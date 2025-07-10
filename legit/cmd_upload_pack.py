from __future__ import annotations

import re

from legit.cmd_base import Base
from legit.remote_agent import RemoteAgentMixin
from legit.send_objects import SendObjectsMixin


class UploadPack(RemoteAgentMixin, SendObjectsMixin, Base):
    CAPABILITIES = ["ofs-delta"]

    def run(self) -> None:
        self.accept_client("upload-pack", self.CAPABILITIES)
        self.send_references()
        self.recv_want_list()
        self.recv_have_list()
        self.send_objects()
        self.exit(0)

    def recv_want_list(self) -> None:
        self.wanted = self.recv_oids("want", None)
        if not self.wanted:
            self.exit(0)

    def recv_oids(self, prefix: str, terminator: bytes | None) -> set[str]:
        pattern = re.compile(f"^{prefix} ([0-9a-f]+)$".encode())
        result = set()

        for line in self.conn.recv_until(terminator):
            m = pattern.match(line)
            if m is not None:
                result.add(m.group(1).decode())

        return result

    def recv_have_list(self) -> None:
        self.remote_has = self.recv_oids("have", b"done")
        self.conn.send_packet(b"NAK")

    def send_objects(self) -> None:
        revs = list(self.wanted) + [f"^{oid}" for oid in self.remote_has]
        self.send_packet_objects(revs)
