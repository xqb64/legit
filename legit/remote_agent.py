from legit.protocol import Remotes
from legit.repository import Repository
from functools import cache
from typing import Optional
from pathlib import Path
from itertools import chain


class RemoteAgentMixin:
    ZERO_OID = b"0" * 40

    def accept_client(self, name, capabilities=None):
        capabilities = capabilities or []

        def as_bin(stream):
            return stream.buffer if hasattr(stream, "buffer") else stream

        self.conn = Remotes.Protocol(
            name, as_bin(self.stdin), as_bin(self.stdout), capabilities
        )

    @property
    @cache
    def repo(self):
        return Repository(self.detect_git_dir())

    def detect_git_dir(self) -> Optional[Path]:
        start: Path = self.expanded_path(self.args[0])

        for ancestor in chain([start], start.parents):
            for candidate in (ancestor, ancestor / ".git"):
                if self.is_git_repository(candidate):
                    return candidate

        return None

    def is_git_repository(self, dirname) -> None:
        return (
            (dirname / "HEAD").exists()
            and (dirname / "objects").exists()
            and (dirname / "refs").exists()
        )

    def send_references(self):
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
