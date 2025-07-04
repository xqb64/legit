from collections import defaultdict
from pathlib import Path

class Trie:
    """
    A trie node that tracks whether the path represented
    by the sequence of keys is "matched" and has children nodes.
    """
    __slots__ = ('matched', 'children')

    def __init__(self, matched: bool = False, children=None):
        self.matched = matched
        # children is a defaultdict that auto-creates sub-tries
        self.children = children if children is not None else defaultdict(Trie.node)

    @classmethod
    def node(cls):
        """Create an empty (unmatched) node with an auto-vending children dict."""
        return cls(False, defaultdict(cls.node))

    @classmethod
    def from_paths(cls, paths):
        """
        Build a trie from an iterable of path strings:
        each path is split on filesystem separators, and the
        terminal node is marked.
        If `paths` is empty, the root is marked.
        """
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
    """
    Filters filesystem-like entries based on a set of allowed
    paths, represented by a Trie.
    """
    __slots__ = ('_routes', 'path')

    def __init__(self, routes: Trie = None, path: Path = None):
        # Default to a fully-matched root if no routes provided
        self._routes = routes if routes is not None else Trie(True)
        # Current Path context (relative)
        self.path = path if path is not None else Path()

    @classmethod
    def build(cls, paths):
        """Construct a PathFilter that matches exactly the given paths."""
        return cls(Trie.from_paths(paths))

    def each_entry(self, entries):
        """
        Iterate over a dict of { name: entry }, yielding only those
        names that are either under a matched route or have a child route.
        """
        for name, entry in entries.items():
            if self._routes.matched or name in self._routes.children:
                yield name, entry

    def join(self, name: str):
        """
        Descend into the sub-path `name`. If current routes are
        already matched (wildcard), reuse them; otherwise create
        or fetch the child node. Returns a new PathFilter with
        updated routes and path context.
        """
        next_routes = self._routes if self._routes.matched else self._routes.children[name]
        return PathFilter(next_routes, self.path / name)

