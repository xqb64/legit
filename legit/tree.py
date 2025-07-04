from legit.index import Entry
from typing import Any, Callable, MutableMapping
from pathlib import Path


def git_sort_key(item):
    name, entry = item
    if isinstance(entry, Tree):
        return name + "/"
    return name



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
            self.oid  == other.oid  and
            self.mode == other.mode and
            self.is_tree() == other.is_tree()
        )
class Tree:
    def __init__(self, entries: MutableMapping[str, 'DatabaseEntry | Entry | Tree'] | None = None) -> None:
        self.entries: MutableMapping[str, DatabaseEntry | Entry | Tree] = (
            entries if entries is not None else {} 
        )
        self.oid: str = ''

    @classmethod
    def parse(cls, payload: bytes) -> "Tree":
        """
        Parse the body of a git tree object:

            <mode> SP <name> NUL <20-byte raw SHA-1>
            … repeated until end of payload
        """
        entries: MutableMapping[str, DatabaseEntry | Entry | Tree] = {}
        idx = 0
        end = len(payload)

        while idx < end:
            # mode (octal string up to the first space)
            sp = payload.index(b" ", idx)
            mode = int(payload[idx:sp].decode(), 8)
            idx = sp + 1

            # name (utf-8 up to NULL)
            nul = payload.index(b"\x00", idx)
            name = payload[idx:nul].decode("utf-8", errors="replace")
            idx = nul + 1

            # 20-byte object id 
            oid_bytes = payload[idx : idx + 20]
            oid = oid_bytes.hex()
            idx += 20

            entries[name] = DatabaseEntry(oid=oid, mode=mode)

        return cls(entries)
    
    @classmethod
    def from_entries(cls, entries: dict[Path, Entry]) -> 'Tree':
        entries = dict(sorted(entries.items(), key=lambda x: x[1].path))

        root = Tree()

        for _, entry in entries.items():
            root.add_entry(entry.parent_directories(), entry)

        return root
    
    def add_entry(self, parents: list[Path], entry: Entry) -> None:
        if not parents:
            self.entries[entry.basename()] = entry
        else:
            head = parents[0]
            tree = self.entries.setdefault(str(head.name), Tree())
            assert isinstance(tree, Tree)
            tree.add_entry(parents[1:], entry)

    def type(self) -> str:
        return "tree"

    def to_bytes(self) -> bytes:
        parts = []
        for name, entry in sorted(self.entries.items(), key=git_sort_key):
            if isinstance(entry, Tree):
                mode_str = '40000'
                assert entry.oid is not None
                oid = entry.oid
            else:
                assert not isinstance(entry, DatabaseEntry)
                m = entry.mode()
                mode_str = oct(m)[2:]
                oid = entry.oid

            header = f"{mode_str} {name}".encode("utf-8") + b"\x00"
            sha = bytes.fromhex(oid)
            parts.append(header + sha)
        return b"".join(parts)

    def traverse(self, code: Callable[['Tree'], None]) -> None:
        for name, entry in self.entries.items():
            if isinstance(entry, Tree):
                entry.traverse(code)
        code(self)


