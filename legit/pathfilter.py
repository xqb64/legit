from collections import defaultdict
from pathlib import Path


class Trie:
    __slots__ = ("matched", "children")

    def __init__(self, matched: bool = False, children=None):
        self.matched = matched
        self.children = children if children is not None else defaultdict(Trie.node)

    @classmethod
    def node(cls):
        return cls(False, defaultdict(cls.node))

    @classmethod
    def from_paths(cls, paths):
        root = cls.node()
        if not paths:
            root.matched = True

        for p in paths:
            trie = root
            path = Path(p)
            for part in path.parts:
                trie = trie.children[part]
            trie.matched = True

        return root


class PathFilter:
    __slots__ = ("_routes", "path")

    def __init__(self, routes: Trie = None, path: Path = None):
        self._routes = routes if routes is not None else Trie(True)
        self.path = path if path is not None else Path()

    @classmethod
    def build(cls, paths):
        return cls(Trie.from_paths(paths))

    def each_entry(self, entries):
        for name, entry in entries.items():
            if self._routes.matched or name in self._routes.children:
                yield name, entry

    def join(self, name: str):
        next_routes = (
            self._routes if self._routes.matched else self._routes.children[name]
        )
        return PathFilter(next_routes, self.path / name)
