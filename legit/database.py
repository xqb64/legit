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
from legit.temp_file import TempFile
from legit.db_loose import Loose, Raw
from legit.db_backends import Backends


TYPES: MutableMapping[str, Type[Blob | Commit | Tree]] = {
    "blob": Blob,
    "commit": Commit,
    "tree": Tree,
}


class Database:
    TYPES = {
        "blob": Blob,
        "commit": Commit,
        "tree": Tree,
    }

    def __init__(self, path: Path) -> None:
        self.path: Path = path
        self.objects: MutableMapping[str, Blob | Commit | Tree] = {}
        self.backend = Backends(self.path)

    def has(self, oid: str) -> bool:
        return self.backend.has(oid)

    def load_info(self, oid: str) -> Raw:
        return self.backend.load_info(oid)

    def load_raw(self, oid: str) -> Raw:
        return self.backend.load_raw(oid)

    def prefix_match(self, name: str) -> list[str]:
        return self.backend.prefix_match(name)

    def write_object(self, oid: str, content: bytes) -> None:
        return self.backend.write_object(oid, content)

    @property
    def pack_path(self):
        return self.path / "pack"

    def read_object(self, oid):
        """
        Read and parse a Git object by oid, returning the parsed object with its oid set.
        """
        raw = self.load_raw(oid)
        obj = TYPES[raw.ty].parse(raw.data)
        obj.oid = oid
        return obj

    def tree_entry(self, oid: str) -> DatabaseEntry:
        return DatabaseEntry(oid, 0o40000)

    def tree_diff(
        self, a: str, b: str, pathfilter=PathFilter()
    ) -> dict[Path, list[Optional[DatabaseEntry]]]:
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
        header = f"{obj.type()} {len(string)}".encode("utf-8") + b"\x00"

        return header + string

    def hash_content(self, content: bytes) -> str:
        return hashlib.sha1(content).hexdigest()

    def short_oid(self, oid: str) -> str:
        return oid[:7]

    def generate_temp_name(self) -> str:
        return f"tmp_obj_" + "".join(
            random.choices(string.ascii_letters + string.digits, k=6)
        )
