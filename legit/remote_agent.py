from legit.protocol import Remotes
from legit.repository import Repository
from functools import cache


class RemoteAgentMixin:
    ZERO_OID = "0" * 40

    def accept_client(self, name, capabilities=[]):
        self.conn = Remotes.Protocol(name, self.stdin, self.stdout, capabilities)
    
    @property
    @cache
    def repo(self):
        return Repository(self.detect_git_dir())

    def detect_git_dir(self):
        path = self.expanded_pathname(self.args[0])
        ancestors = (path,) + path.parents 

        dirs = [p
            for ancestor in ancestors
            for p in (ancestor, ancestor / ".git")
        ]

        return [d for d in dirs if self.is_git_repository(d)][0]

    def is_git_repository(self, dirname) -> None:
        return (dirname / "HEAD").exists() and (dirname / "objects").exists() and (dirname / "refs").exists()

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
