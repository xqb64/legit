from pathlib import Path
from typing import Optional, cast, TYPE_CHECKING

from legit.blob import Blob
from legit.commit import Commit

if TYPE_CHECKING:
    from legit.database import Database
else:
    Database = None

from legit.index import Entry
from legit.tree import DatabaseEntry, Tree


class TreeDiff:
    def __init__(self, database: Database) -> None:
        self.database: Database = database
        self.changes: dict[Path, list[Optional[DatabaseEntry]]] = {}

    def compare_oids(self, a: Optional[str], b: Optional[str], pathfilter) -> None:
        if a == b:
            return

        a_tree = self.oid_to_tree(a)
        b_tree = self.oid_to_tree(b)

        a_entries = cast(
            dict[Path, DatabaseEntry],
            ({k: v for k, v in a_tree.entries.items()} if a_tree else {}),
        )
        b_entries = cast(
            dict[Path, DatabaseEntry],
            ({k: v for k, v in b_tree.entries.items()} if b_tree else {}),
        )

        self.detect_deletions(a_entries, b_entries, pathfilter)
        self.detect_additions(a_entries, b_entries, pathfilter)

    def oid_to_tree(self, oid: Optional[str]) -> Optional[Tree]:
        if oid is None:
            return None

        obj = self.database.load(oid)

        if obj.type() == "commit":
            assert not isinstance(obj, Blob)
            assert not isinstance(obj, Tree)
            assert isinstance(obj, Commit)
            tree = self.database.load(obj.tree)
            assert isinstance(tree, Tree)
            return tree
        elif obj.type() == "tree":
            assert not isinstance(obj, Blob)
            assert not isinstance(obj, Commit)
            assert isinstance(obj, Tree)
            return obj
        else:
            return None

    def detect_deletions(self, a: dict, b: dict, path_filter) -> None:
        for name, entry in path_filter.each_entry(a):
            other = b.get(name)
            if entry == other:
                continue

            sub_filter = path_filter.join(name)

            tree_a = entry.oid if entry and entry.is_tree() else None
            tree_b = other.oid if other and other.is_tree() else None
            self.compare_oids(tree_a, tree_b, sub_filter)

            blobs = [None if (e and e.is_tree()) else e for e in (entry, other)]
            if any(blobs):
                self.changes[sub_filter.path] = blobs

    def detect_additions(self, a: dict, b: dict, path_filter) -> None:
        for name, entry in path_filter.each_entry(b):
            other = a.get(name)
            if other is not None:
                continue

            sub_filter = path_filter.join(name)

            if entry.is_tree():
                self.compare_oids(None, entry.oid, sub_filter)
            else:
                self.changes[sub_filter.path] = [None, entry]
