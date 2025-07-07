from legit.protocol import Remotes
from legit.repository import Repository
from functools import cache
from typing import Optional
from pathlib import Path
from itertools import chain


class RemoteAgentMixin:
    ZERO_OID = "0" * 40

    def accept_client(self, name, capabilities=[]):
        self.conn = Remotes.Protocol(name, self.stdin, self.stdout, capabilities)

    @property
    @cache
    def repo(self):
        return Repository(self.detect_git_dir())

    def detect_git_dir(self) -> Optional[Path]:
        """
        Walk up from `self.args[0]`, returning the first directory that is
        (a) itself a Git repository *or* (b) contains a `.git` directory.

        Returns ``None`` if nothing is found.
        """
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
            self.conn.send_packet(f"{oid.lower()} {symref.path}")
            sent = True

        if not sent:
            self.conn.send_packet(f"{self.ZERO_OID} capabilities^{{}}")

        self.conn.send_packet(None)
