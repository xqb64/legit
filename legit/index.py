import os
import stat
import struct
import hashlib
from legit.lockfile import Lockfile
from pathlib import Path
from collections import defaultdict
from typing import BinaryIO

from typing import BinaryIO, Protocol, runtime_checkable


@runtime_checkable
class Hash(Protocol):
    def update(self, data: bytes) -> None: ...
    def digest(self) -> bytes: ...


def _u32(x: int) -> int:
    """Return the lower 32 bits of x (Git index uses uint32)."""
    return x & 0xFFFFFFFF


class Index:
    HEADER_SIZE: int = 12
    HEADER_FORMAT: str = ">4sII"
    SIGNATURE: bytes = b"DIRC"
    VERSION: int = 2

    ENTRY_BLOCK: int = 8
    ENTRY_MIN_SIZE: int = 64

    def __init__(self, path: Path) -> None:
        self.path: Path = path
        self.entries: dict[tuple[Path, int], Entry] = {}
        self.lockfile: Lockfile = Lockfile(path)
        self.digest: Hash | None = None
        self.changed: bool = False
        self.parents: dict[Path, set[Path]] = defaultdict(set)

    def conflict_paths(self):
        paths = set()
        for entry in self.entries.values():
            if entry.stage != 0:
                paths.add(entry)
        return paths

    def add_from_db(self, path: Path, item) -> None:
        self.store_entry(Entry.create_from_db(path, item, 0))
        self.changed = True

    def child_paths(self, path: Path) -> list[Path]:
        return list(self.parents[path])

    def is_tracked_directory(self, path: Path) -> bool:
        return path in self.parents

    def is_conflict(self) -> bool:
        return any(stage > 0 for _, stage in self.entries)

    def add_conflict_set(self, path: Path, items) -> None:
        self.remove_entry_with_stage(path, 0)

        for idx, item in enumerate(items):
            if not item:
                continue

            entry = Entry.create_from_db(path, item, idx + 1)
            self.store_entry(entry)

        self.changed = True

    def update_entry_stat(self, entry: "Entry", stat: os.stat_result) -> None:
        entry.update_stat(stat)
        self.changed = True

    def entry_for_path(self, path: Path, stage: int = 0) -> " Entry | None":
        return self.entries.get((path, stage))

    def is_tracked_file(self, path: Path) -> bool:
        for i in range(4):
            if (path, i) in self.entries:
                return True
        return False

    def is_tracked(self, path: Path) -> bool:
        return self.is_tracked_file(path) or path in self.parents

    def release_lock(self) -> None:
        self.lockfile.rollback()

    def add(self, path: Path, oid: str, stat: os.stat_result) -> None:
        for stage in range(1, 4):
            self.remove_entry_with_stage(path, stage)

        path = Path(path) if not isinstance(path, Path) else path
        entry: Entry = Entry.create(path, oid, stat)
        self.discard_conflicts(entry)
        self.store_entry(entry)
        self.changed = True

    def remove(self, path: Path) -> None:
        self.remove_entry(path)
        self.remove_children(path)
        self.changed = True

    def discard_conflicts(self, entry: "Entry") -> None:
        for dirname in entry.parent_directories():
            self.remove_entry(dirname)
        self.remove_children(entry.path)

    def remove_entry(self, path: Path) -> None:
        for stage in range(4):
            self.remove_entry_with_stage(path, stage)

    def remove_entry_with_stage(self, path: Path, stage: int) -> None:
        entry = self.entries.get((path, stage))
        if entry is None:
            return

        self.entries.pop(entry.key(), None)

        for dirname in entry.parent_directories():
            paths = self.parents.get(dirname)
            if not paths:
                continue

            paths.discard(entry.path)
            if not paths:
                del self.parents[dirname]

    def remove_children(self, path: Path) -> None:
        if path not in self.parents:
            return

        children = self.parents[path]

        for child in children.copy():
            self.remove_entry(child)

    def write_updates(self) -> None:
        if not self.changed:
            return self.lockfile.rollback()

        assert self.lockfile.lock is not None
        writer: Checksum = Checksum(self.lockfile.lock)

        header: bytes = struct.pack(
            Index.HEADER_FORMAT, Index.SIGNATURE, Index.VERSION, len(self.entries)
        )
        writer.write(header)

        for _, v in sorted(self.entries.items()):
            writer.write(v.to_bytes())

        writer.write_checksum()
        self.lockfile.commit()

        self.changed = False

    def load_for_update(self) -> None:
        self.lockfile.hold_for_update()
        self.load()

    def load(self) -> None:
        self._clear()

        file = self.open_index_file()

        if file is not None:
            reader = Checksum(file)
            count = self.read_header(reader)
            self.read_entries(reader, count)
            reader.verify_checksum()

            file.close()

    def clear(self) -> None:
        self._clear()
        self.changed = True

    def _clear(self) -> None:
        self.entries = {}
        self.changed = False
        self.parents = defaultdict(set)

    def open_index_file(self) -> BinaryIO | None:
        try:
            return open(self.path, "rb")
        except FileNotFoundError:
            return None

    def read_header(self, reader: "Checksum") -> int:
        data = reader.read(Index.HEADER_SIZE)

        signature: bytes
        version: int
        count: int

        signature, version, count = struct.unpack(Index.HEADER_FORMAT, data)

        if signature != Index.SIGNATURE:
            raise Exception("Invalid signature.")

        if version != Index.VERSION:
            raise Exception("Invalid version")

        return count

    def read_entries(self, reader: "Checksum", count: int) -> None:
        for _ in range(count):
            entry = reader.read(Index.ENTRY_MIN_SIZE)

            while entry[-1:] != b"\x00":  # Ensure slicing result is bytes
                entry += reader.read(Index.ENTRY_BLOCK)

            self.store_entry(Entry.parse(entry))

    def store_entry(self, entry: "Entry") -> None:
        self.entries[entry.key()] = entry
        for dirname in entry.parent_directories():
            self.parents[dirname].add(entry.path)

    def begin_write(self) -> None:
        self.digest = hashlib.sha1()

    def write(self, data: bytes) -> None:
        self.lockfile.write(data)
        assert self.digest is not None
        self.digest.update(data)

    def finish_write(self) -> None:
        assert self.digest is not None
        self.lockfile.write(self.digest.digest())
        self.lockfile.commit()


class Entry:
    REGULAR_MODE: int = 0o100644
    EXECUTABLE_MODE: int = 0o100755
    MAX_PATH_SIZE: int = 0xFFF
    ENTRY_BLOCK: int = 8
    HEADER_FORMAT: str = "!10I20sH"
    HEADER_SIZE: int = struct.calcsize(HEADER_FORMAT)

    def __init__(
        self,
        ctime: float,
        ctime_nsec: int,
        mtime: float,
        mtime_nsec: int,
        dev: int,
        ino: int,
        mode: int,
        uid: int,
        gid: int,
        size: int,
        oid: str,
        flags: int,
        path: Path,
    ):
        self.ctime = ctime
        self.ctime_nsec = ctime_nsec
        self.mtime = mtime
        self.mtime_nsec = mtime_nsec
        self.dev = dev
        self.ino = ino
        self._mode = mode
        self.uid = uid
        self.gid = gid
        self.size = size
        self.oid = oid
        self.flags = flags
        self.path = path

    @classmethod
    def create_from_db(cls, path: Path, item, n: int) -> "Entry":
        p = str(path)
        flags = (n << 12) | min(len(p), Entry.MAX_PATH_SIZE)
        return cls(0, 0, 0, 0, 0, 0, item.mode, 0, 0, 0, item.oid, flags, path)

    @property
    def stage(self) -> int:
        return (self.flags >> 12) & 0x3

    def update_stat(self, stat_result: os.stat_result) -> None:
        self.ctime = int(stat_result.st_ctime)
        self.ctime_nsec = stat_result.st_ctime_ns
        self.mtime = int(stat_result.st_mtime)
        self.mtime_nsec = stat_result.st_mtime_ns
        self.dev = stat_result.st_dev
        self.ino = stat_result.st_ino
        self._mode = Entry.mode_for_stat(stat_result)
        self.uid = stat_result.st_uid
        self.gid = stat_result.st_gid
        self.size = stat_result.st_size

    @staticmethod
    def mode_for_stat(stat_result: os.stat_result) -> int:
        exec_perms: int = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        is_executable: bool = bool(stat_result.st_mode & exec_perms)
        return Entry.REGULAR_MODE if not is_executable else Entry.EXECUTABLE_MODE

    def stat_match(self, stat_result: os.stat_result) -> bool:
        return self._mode == Entry.mode_for_stat(stat_result) and (
            self.size == 0 or self.size == stat_result.st_size
        )

    def times_match(self, stat_result: os.stat_result) -> bool:
        return (
            self.ctime == int(stat_result.st_ctime)
            and self.ctime_nsec == stat_result.st_ctime_ns
            and self.mtime == int(stat_result.st_mtime)
            and self.mtime_nsec == stat_result.st_mtime_ns
        )

    def mode(self) -> int:
        return self._mode

    def basename(self) -> str:
        p = Path(self.path).name
        return p

    def parent_directories(self) -> list[Path]:
        parts = Path(self.path).parts
        return [Path(*parts[: i + 1]) for i in range(len(parts) - 1)]

    @classmethod
    def parse(cls, data: bytes) -> "Entry":
        """
        Parses a byte string to create an Entry instance.
        This is the inverse of the to_bytes method.
        """
        import binascii

        # Unpack the fixed-size part of the data
        header_data = data[: cls.HEADER_SIZE]
        unpacked_header = struct.unpack(cls.HEADER_FORMAT, header_data)

        # Extract the metadata fields from the unpacked tuple
        (ctime, ctime_nsec, mtime, mtime_nsec, dev, ino, mode, uid, gid, size) = (
            unpacked_header[:10]
        )

        # The OID is the next part, convert the 20 bytes back to a hex string
        oid_bytes = unpacked_header[10]
        oid_hex = binascii.hexlify(oid_bytes).decode("ascii")

        # The flags are the last part of the fixed header
        flags = unpacked_header[11]

        # The rest of the data contains the path. Find the first null byte.
        path_start_index = cls.HEADER_SIZE
        try:
            null_index = data.index(b"\x00", path_start_index)
            path_bytes = data[path_start_index:null_index]
            path = Path(path_bytes.decode("utf-8"))
        except ValueError:
            # Fallback if no null terminator is found (should not happen with valid data)
            path = Path(data[path_start_index:].decode("utf-8", "ignore"))

        # Construct the Entry object with the parsed data
        return cls(
            ctime,
            ctime_nsec,
            mtime,
            mtime_nsec,
            dev,
            ino,
            mode,
            uid,
            gid,
            size,
            oid_hex,
            flags,
            path,
        )

    @classmethod
    def create(cls, path: Path, oid: str, _stat: os.stat_result) -> "Entry":
        path = Path(path) if not isinstance(path, Path) else path
        exec_perms = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        is_executable = bool(_stat.st_mode & exec_perms)
        mode = Entry.EXECUTABLE_MODE if is_executable else Entry.REGULAR_MODE
        flags = min(len(str(path).encode("utf-8")), Entry.MAX_PATH_SIZE)

        return cls(
            _stat.st_ctime,
            _stat.st_ctime_ns,
            _stat.st_mtime,
            _stat.st_mtime_ns,
            _stat.st_dev,
            _stat.st_ino,
            mode,
            _stat.st_uid,
            _stat.st_gid,
            _stat.st_size,
            oid,
            flags,
            path,
        )

    def to_bytes(self) -> bytes:
        import binascii

        header = struct.pack(
            "!10I",
            _u32(int(self.ctime)),
            _u32(self.ctime_nsec),
            _u32(int(self.mtime)),
            _u32(self.mtime_nsec),
            _u32(self.dev),
            _u32(self.ino),
            _u32(self._mode),
            _u32(self.uid),
            _u32(self.gid),
            _u32(self.size),
        )

        # 20 raw bytes from 40-char hex OID
        oid_bytes = binascii.unhexlify(self.oid)

        # 2-byte unsigned short for flags
        flags = struct.pack("!H", self.flags)

        # Null-terminated path
        path_bytes = str(self.path).encode("utf-8") + b"\x00"

        result = header + oid_bytes + flags + path_bytes

        # Pad to ENTRY_BLOCK (8-byte) boundary
        while len(result) % Entry.ENTRY_BLOCK != 0:
            result += b"\x00"

        return result

    def key(self) -> tuple[Path, int]:
        return (self.path, self.stage)


class Checksum:
    class EndOfFile(Exception):
        pass

    CHECKSUM_SIZE = 20

    def __init__(self, file: BinaryIO) -> None:
        self.file: BinaryIO = file
        self.digest = hashlib.sha1()

    def write(self, data: bytes) -> None:
        self.file.write(data)
        self.digest.update(data)

    def write_checksum(self) -> None:
        self.file.write(self.digest.digest())

    def read(self, size: int) -> bytes:
        data = self.file.read(size)

        if len(data) != size:
            raise Checksum.EndOfFile

        self.digest.update(data)
        return data

    def verify_checksum(self) -> None:
        remaining = self.file.read()
        data = remaining[: -self.CHECKSUM_SIZE]
        stored_checksum = remaining[-self.CHECKSUM_SIZE :]
        self.digest.update(data)
        if stored_checksum != self.digest.digest():
            raise Exception("Checksum does not match data stored on disk.")
