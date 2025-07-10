from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Generator

from legit.db_entry import DatabaseEntry


class Trie:
    __slots__ = ("matched", "children")

    def __init__(
        self, matched: bool = False, children: defaultdict[Path, "Trie"] | None = None
    ) -> None:
        self.matched = matched
        self.children = children if children is not None else defaultdict(Trie.node)

    @classmethod
    def node(cls) -> "Trie":
        return cls(False, defaultdict(cls.node))

    @classmethod
    def from_paths(cls, paths: list[Path]) -> "Trie":
        root = cls.node()
        if not paths:
            root.matched = True

        for path in paths:
            trie = root
            for part in path.parts:
                trie = trie.children[Path(part)]
            trie.matched = True

        return root


class PathFilter:
    __slots__ = ("_routes", "path")

    def __init__(self, routes: Trie | None = None, path: Path | None = None) -> None:
        self._routes: Trie = routes if routes is not None else Trie(True)
        self.path: Path = path if path is not None else Path()

    @classmethod
    def build(cls, paths: list[Path]) -> "PathFilter":
        return cls(Trie.from_paths(paths))

    def each_entry(
        self, entries: dict[Path, DatabaseEntry]
    ) -> Generator[tuple[Path, DatabaseEntry]]:
        for name, entry in entries.items():
            if self._routes.matched or name in self._routes.children:
                yield name, entry

    def join(self, name: Path) -> "PathFilter":
        next_routes = (
            self._routes if self._routes.matched else self._routes.children[name]
        )
        return PathFilter(next_routes, self.path / name)
