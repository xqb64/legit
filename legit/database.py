import hashlib
from typing import MutableMapping, Optional, Type
import zlib
import os
import random
import string
from pathlib import Path
from legit.tree import DatabaseEntry, Tree
from legit.commit import Commit
from legit.blob import Blob
from legit.tree_diff import TreeDiff
from legit.pathfilter import PathFilter


TYPES: MutableMapping[str, Type[Blob | Commit | Tree]] = {
    "blob": Blob,
    "commit": Commit,
    "tree": Tree,
}


class Raw:
    def __init__(self, ty, size, data):
        self.ty = ty
        self.size = size
        self.data = data


class Database:
    TYPES = {
        "blob": Blob,
        "commit": Commit,
        "tree": Tree,
    }

    def __init__(self, path: Path) -> None:
        self.path: Path = path
        self.objects: MutableMapping[str, Blob | Commit | Tree] = {}


    def load_info(self, oid: str) -> Raw:
        ty, size, _ = self.read_object_header(oid, 128)
        return Raw(ty, size, None)


    def has(self, oid: str) -> bool:
        object_path = self.path / str(oid[:2]) / str(oid[2:])
        return object_path.exists()

    def load_raw(self, oid):
        """
        Load a raw Git object by its oid, returning a Raw(type, size, data) instance.
        """
        ty, size, rest = self.read_object_header(oid)
        return Raw(ty, size, rest)
    
    def read_object_header(self, oid, read_bytes=None, *, chunk_size: int = 8192):
        """
        Read the Git object header for *oid* using a streaming inflater.
    
        Parameters
        ----------
        oid : str | bytes
            The object ID (40-hex SHA-1 or similar).
        read_bytes : int | None
            If given, read at most this many compressed bytes from disk.  This is
            just an upper bound; the function may fetch more in order to complete
            the header.
        chunk_size : int, keyword-only
            Size of each chunk fed to the decompressor when incremental reads are
            required.  Defaults to 8 KiB.
    
        Returns
        -------
        tuple[str, int, bytes]
            (type, size, remainder_bytes)
        """
        # Build “…/.git/objects/ab/cdef…”
        path = Path(self.path) / oid[:2] / oid[2:]
        decomp = zlib.decompressobj()
    
        decompressed = bytearray()
    
        # Helper that streams just enough data to parse the header (up to the NUL).
        def _fill_until_header_complete(fh):
            nonlocal decompressed
            while b'\x00' not in decompressed:
                chunk = fh.read(chunk_size)
                if not chunk:                        # EOF before header finished
                    break
                decompressed += decomp.decompress(chunk)
    
        # ------------------------------------------------------------------ I/O --
        with open(path, "rb") as fh:
            initial = fh.read(read_bytes) if read_bytes else fh.read(chunk_size)
            decompressed += decomp.decompress(initial)
            _fill_until_header_complete(fh)
    
            # Header is now complete ⇒ parse it so we know how many bytes remain.
            space_idx = decompressed.index(b" ")
            null_idx  = decompressed.index(b"\x00", space_idx + 1)
            obj_type  = decompressed[:space_idx].decode()
            obj_size  = int(decompressed[space_idx + 1:null_idx].decode())
    
            # How many bytes of payload have we already got?
            got_payload = len(decompressed) - (null_idx + 1)
            bytes_needed = obj_size - got_payload
    
            # Stream the rest of the payload only if we still need more.
            while bytes_needed > 0:
                chunk = fh.read(chunk_size)
                if not chunk:
                    break                             # corrupted object: premature EOF
                out = decomp.decompress(chunk)
                decompressed += out
                bytes_needed -= len(out)
    
        # Flush any remaining buffered output from the inflater.
        decompressed += decomp.flush()
    
        # Split header and payload once more (in case the size was 0).
        space_idx = decompressed.index(b" ")
        null_idx  = decompressed.index(b"\x00", space_idx + 1)
        rest      = bytes(decompressed[null_idx + 1:])
    
        return obj_type, obj_size, rest

#    def read_object_header(self, oid, read_bytes=None):
#        """
#        Read the Git object header for oid. Optionally read only the first read_bytes from file.
#        Returns (type, size, remainder_bytes).
#        """
#        path = self.path / str(oid[:2]) / str(oid[2:])
#        with open(path, 'rb') as f:
#            raw = f.read(read_bytes) if read_bytes else f.read()
#    
#        data = zlib.decompress(raw)
#        space_idx = data.find(b' ')
#        type_ = data[:space_idx].decode('utf-8')
#        null_idx = data.find(b'\x00', space_idx + 1)
#        size = int(data[space_idx + 1:null_idx].decode('utf-8'))
#        rest = data[null_idx + 1:]
#    
#        return type_, size, rest
    
    def read_object(self, oid):
        """
        Read and parse a Git object by oid, returning the parsed object with its oid set.
        """
        type_, _, rest = self.read_object_header(oid)
        obj = TYPES[type_].parse(rest)
        obj.oid = oid
        return obj

    def tree_entry(self, oid: str) -> DatabaseEntry:
        return DatabaseEntry(oid, 0o40000)
    
    def tree_diff(self, a: str, b: str, pathfilter=PathFilter()) -> dict[Path, list[Optional[DatabaseEntry]]]:
        diff = TreeDiff(self)
        diff.compare_oids(a, b, pathfilter)
        return diff.changes

    def load(self, oid: str) -> Blob | Commit | Tree:
        obj = self.read_object(oid)
        self.objects[oid] = obj
        return obj

    def load_tree_entry(self, oid: str, path: Optional[Path]) -> DatabaseEntry:
        commit = self.load(oid)
        root = DatabaseEntry(commit.tree, 0o40000)

        if path is None:
            return root

        return self.traverse_path_loop(path, root)

    def traverse_path_loop(self, path: Path, root) -> DatabaseEntry:
        entry = root
        for name in path.parts:
            if not entry:
                break
            entry = self.load(entry.oid).entries.get(name)
        return entry

    def load_tree_list(self, oid: Optional[str], path: Optional[Path] = None):
        if oid is None:
            return {}

        entry = self.load_tree_entry(oid, path)
        thing = {}
        self.build_list(thing, entry, path if path is not None else Path())
        return thing

    def build_list(self, thing, entry, prefix: Path):
        if entry is None:
            return

        if not entry.is_tree():
            thing[prefix] = entry
            return entry
        
        for name, item in self.load(entry.oid).entries.items():
            self.build_list(thing, item, prefix / name)
    
    def store(self, obj: Blob | Commit | Tree) -> None:
        content = self.serialize_object(obj)
        obj.oid = self.hash_content(content)
        
        self.write_object(obj.oid, content)

    def hash_object(self, obj: Blob | Commit | Tree) -> str:
        return self.hash_content(self.serialize_object(obj))

    def serialize_object(self, obj: Blob | Commit | Tree) -> bytes:
        string = obj.to_bytes()
        header = f"{obj.type()} {len(string)}".encode('utf-8') + b"\x00"

        return header + string

    def hash_content(self, content: bytes) -> str:
        return hashlib.sha1(content).hexdigest()
 
    def write_object(self, oid: str, content: bytes) -> None:
        object_path = self.path / str(oid[:2]) / str(oid[2:])
        if object_path.exists():
            return

        dirname = object_path.parent
        temp_path = dirname / self.generate_temp_name()

        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
        mode = 0o644

        try:
            file = os.fdopen(os.open(temp_path, flags, mode), "rb+")
        except FileNotFoundError:
            dirname.mkdir(exist_ok=True, parents=True)
            file = os.fdopen(os.open(temp_path, flags, mode), "rb+")

        compressed = zlib.compress(content)
        file.write(compressed)
        file.close()

        temp_path.rename(object_path)

    def prefix_match(self, name: str) -> list[str]:
        object_path = self.path / str(name[:2]) / str(name[2:])
        dirname = object_path.parent

        oids = []
        
        try:
            files = dirname.iterdir()
        except FileNotFoundError:
            return []

        for filename in files:
            oids.append(f"{dirname.name}{filename.name}")

        return [oid for oid in oids if oid.startswith(name)]

    def short_oid(self, oid: str) -> str:
        return oid[:7]

    def generate_temp_name(self) -> str:
        return f"tmp_obj_" + ''.join(random.choices(string.ascii_letters + string.digits, k=6))
            
        


