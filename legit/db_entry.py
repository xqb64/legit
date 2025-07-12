from __future__ import annotations

from typing import Any


class DatabaseEntry:
    TREE_MODE = 0o40000

    def __init__(self, oid: str, mode: int) -> None:
        self.oid: str = oid
        self.mode: int = mode

    def is_tree(self) -> bool:
        return self.mode == DatabaseEntry.TREE_MODE

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, DatabaseEntry):
            return NotImplemented
        return (
            self.oid == other.oid
            and self.mode == other.mode
            and self.is_tree() == other.is_tree()
        )
