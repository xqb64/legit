from __future__ import annotations

from functools import cache
from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO, Optional, TextIO, cast

from legit.protocol import Remotes
from legit.repository import Repository


class RemoteAgentMixin:
    args: list[str]
    stdin: TextIO
    stdout: TextIO

    if TYPE_CHECKING:

        def expanded_path(self, path: str) -> Path: ...

    ZERO_OID: bytes = b"0" * 40

    def accept_client(self, name: str, capabilities: list[str] | None = None) -> None:
        capabilities = capabilities or []

        def as_bin(stream: TextIO) -> BinaryIO | TextIO:
            return stream.buffer if hasattr(stream, "buffer") else stream

        self.conn = Remotes.Protocol(
            name,
            cast(BinaryIO, as_bin(self.stdin)),
            cast(BinaryIO, as_bin(self.stdout)),
            capabilities,
        )

    @property
    @cache
    def repo(self) -> Repository:
        path = self.detect_git_dir()
        assert path is not None
        return Repository(path)

    def detect_git_dir(self) -> Optional[Path]:
        start: Path = self.expanded_path(self.args[0])

        for ancestor in chain([start], start.parents):
            for candidate in (ancestor, ancestor / ".git"):
                if self.is_git_repository(candidate):
                    return candidate

        return None

    def is_git_repository(self, dirname: Path) -> bool:
        return (
            (dirname / "HEAD").exists()
            and (dirname / "objects").exists()
            and (dirname / "refs").exists()
        )

    def send_references(self) -> None:
        refs = self.repo.refs.list_all_refs()
        sent = False

        for symref in sorted(refs, key=lambda x: x.path):
            oid = symref.read_oid()
            if oid is None:
                continue
            self.conn.send_packet(f"{oid.lower()} {symref.path}".encode())
            sent = True

        if not sent:
            self.conn.send_packet(f"{'0' * 40} capabilities^{{}}".encode())

        self.conn.send_packet(None)
