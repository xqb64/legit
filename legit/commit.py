from collections import defaultdict
from datetime import datetime
from typing import Optional, cast
from legit.author import Author


class Commit:
    def __init__(
        self,
        parents: list[Optional[str]],
        tree: str,
        author: Author,
        committer: Author,
        message: str,
    ) -> None:
        self.parents: list[Optional[str]] = parents
        self.tree: str = tree
        self.author: Author = author
        self.committer = committer
        self.message: str = message
        self._oid: str | None = None

    def is_merge(self) -> bool:
        return len(self.parents) > 1

    @property
    def parent(self):
        try:
            return self.parents[0]
        except IndexError:
            return None

    @parent.setter
    def parent(self, value):
        if not self.parents:
            self.parents.append(value)
        else:
            self.parents[0] = value

    @classmethod
    def parse(cls, data: bytes) -> "Commit":
        """
        Parse the raw `commit` object payload exactly like the Ruby version.

        * **Multiple headers per key** are kept (e.g. several `parent` lines).
        * We stop at the first *empty* line and treat everything after it as the
          commit message, preserving all newlines exactly.
        * The return value’s first argument is a `list[str]` of parents,
          mirroring the Ruby array, even when it is empty.
        """
        text = data.decode("utf-8", errors="replace")

        headers: dict[str, list[str]] = defaultdict(list)
        pos = 0
        while True:
            nl = text.find("\n", pos)
            if nl == -1:
                raise ValueError("unterminated commit headers")
            line = text[pos:nl]
            pos = nl + 1
            if line == "":
                break

            key, value = line.split(" ", 1)
            headers[key].append(value)

        message = text[pos:]

        tree_values = headers.get("tree")
        if not tree_values:
            raise ValueError("commit object missing 'tree' header")
        author_values = headers.get("author")
        if not author_values:
            raise ValueError("commit object missing 'author' header")

        return cls(
            parents=headers.get("parent", []),
            tree=tree_values[0],
            author=Author.parse(author_values[0]),
            committer=Author.parse(headers.get("committer")[0]),
            message=message,
        )

    @property
    def oid(self) -> str:
        assert self._oid is not None
        return self._oid

    @oid.setter
    def oid(self, value: str) -> None:
        self._oid = value

    def title_line(self) -> str:
        return self.message.splitlines()[0]

    def type(self) -> str:
        return "commit"

    def date(self) -> datetime:
        return self.committer.time

    def to_bytes(self) -> bytes:
        lines = [
            f"tree {self.tree}",
        ]

        for parent in self.parents:
            lines += [f"parent {parent}"]

        lines.extend(
            [
                f"author {self.author}",
                f"committer {self.committer}",
                "",
                self.message,
            ]
        )

        return b"\n".join(line.encode("utf-8") for line in lines)
