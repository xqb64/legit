from __future__ import annotations

import hashlib
import random
import string
from pathlib import Path
from typing import MutableMapping, Optional, Type, cast, reveal_type

from legit.blob import Blob
from legit.commit import Commit
from legit.db_backends import Backends
from legit.db_entry import DatabaseEntry
from legit.db_loose import Raw
from legit.index import Entry
from legit.pack import OfsDelta, Record, RefDelta
from legit.pathfilter import PathFilter
from legit.tree import Tree
from legit.tree_diff import TreeDiff

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

    def close(self) -> None:
        self.backend.close()

    def __del__(self) -> None:
        self.close()

    def __init__(self, path: Path) -> None:
        self.path: Path = path
        self.objects: MutableMapping[str, Blob | Commit | Tree] = {}
        self.backend = Backends(self.path)

    def has(self, oid: str) -> bool:
        return self.backend.has(oid)

    def load_info(self, oid: str) -> Raw | None:
        return self.backend.load_info(oid)

    def load_raw(self, oid: str) -> Raw | Record | OfsDelta | RefDelta | None:
        return self.backend.load_raw(oid)

    def prefix_match(self, name: str) -> list[str]:
        return self.backend.prefix_match(name)

    def write_object(self, oid: str, content: bytes) -> None:
        return self.backend.write_object(oid, content)

    @property
    def pack_path(self) -> Path:
        return self.path / "pack"

    def read_object(self, oid: str) -> Blob | Commit | Tree:
        raw = cast(Raw, self.load_raw(oid))
        obj = TYPES[raw.ty].parse(cast(bytes, raw.data))
        obj.oid = oid
        return obj

    def tree_entry(self, oid: str) -> DatabaseEntry:
        return DatabaseEntry(oid, 0o40000)

    def tree_diff(
        self, a: str, b: str, pathfilter: PathFilter = PathFilter()
    ) -> dict[Path, list[Optional[DatabaseEntry]]]:
        diff = TreeDiff(self)
        diff.compare_oids(a, b, pathfilter)
        return diff.changes

    def load(self, oid: str) -> Blob | Commit | Tree | Record:
        obj = self.read_object(oid)
        self.objects[oid] = obj
        return obj

    def load_tree_entry(
        self, oid: str, path: Optional[Path]
    ) -> DatabaseEntry | Entry | Tree | None:
        commit = self.load(oid)
        root = DatabaseEntry(cast(Commit, commit).tree, 0o40000)

        if path is None:
            return root

        return self.traverse_path_loop(path, root)

    def traverse_path_loop(
        self, path: Path, root: DatabaseEntry
    ) -> DatabaseEntry | Entry | Tree | None:
        entry = root
        for name in path.parts:
            if not entry:
                break
            entry = cast(
                DatabaseEntry, cast(Tree, self.load(entry.oid)).entries.get(name)
            )
        return entry

    def load_tree_list(
        self, oid: Optional[str], path: Optional[Path] = None
    ) -> dict[Path, DatabaseEntry | Entry | Tree | None]:
        if oid is None:
            return {}

        entry = self.load_tree_entry(oid, path)
        thing: dict[Path, DatabaseEntry | Entry | Tree | None] = {}
        self.build_list(thing, entry, path if path is not None else Path())
        return thing

    def build_list(
        self,
        thing: dict[Path, DatabaseEntry | Entry | Tree | None],
        entry: DatabaseEntry | Entry | Tree | None,
        prefix: Path,
    ) -> DatabaseEntry | Entry | Tree | None:
        if entry is None:
            return None

        if not cast(DatabaseEntry, entry).is_tree():
            thing[prefix] = entry
            return entry

        for name, item in cast(Tree, self.load(entry.oid)).entries.items():
            self.build_list(thing, item, prefix / name)

        return None

    def store(self, obj: Blob | Commit | Tree | Record) -> None:
        content = self.serialize_object(obj)
        obj.oid = self.hash_content(content)

        self.write_object(obj.oid, content)

    def hash_object(self, obj: Blob | Commit | Tree | Record) -> str:
        return self.hash_content(self.serialize_object(obj))

    def serialize_object(self, obj: Blob | Commit | Tree | Record) -> bytes:
        string = cast(bytes, obj.to_bytes())
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
