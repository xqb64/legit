from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import cast

from legit.author import Author


class Commit:
    def __init__(
        self,
        parents: list[str],
        tree: str,
        author: Author | None,
        committer: Author | None,
        message: str,
    ) -> None:
        self.parents: list[str] = parents
        self.tree: str = tree
        self.author: Author | None = author
        self.committer: Author | None = committer
        self.message: str = message
        self._oid: str | None = None

    def is_merge(self) -> bool:
        return len(self.parents) > 1

    @property
    def parent(self) -> str | None:
        try:
            return self.parents[0]
        except IndexError:
            return None

    @parent.setter
    def parent(self, value: str) -> None:
        if not self.parents:
            self.parents.append(value)
        else:
            self.parents[0] = value

    @classmethod
    def parse(cls, data: bytes) -> "Commit":
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

        committer_values = headers.get("committer", author_values)
        if not committer_values:
            raise ValueError("commit object missing 'committer' header")

        return cls(
            parents=headers.get("parent", []),
            tree=tree_values[0],
            author=Author.parse(author_values[0]),
            committer=Author.parse(committer_values[0]),
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
        return cast(Author, self.committer).time

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
