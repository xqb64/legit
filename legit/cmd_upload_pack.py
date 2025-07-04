import re
from legit.cmd_base import Base
from legit.remote_agent import RemoteAgentMixin
from legit.send_objects import SendObjectsMixin


class UploadPack(RemoteAgentMixin, SendObjectsMixin, Base):
    def run(self) -> None:
        self.accept_client("upload-pack")

        self.send_references()
        self.recv_want_list()
        self.recv_have_list()

        self.send_objects()

        self.exit(0)

    def recv_want_list(self):
        self.wanted = self.recv_oids("want", None)
        if not self.wanted:
            self.exit(0)

    def recv_oids(self, prefix, terminator):
        pattern = re.compile(f"^{prefix} ([0-9a-f]+)$")
        result = set()

        for line in self.conn.recv_until(terminator):
            m = pattern.match(line)
            result.add(m.group(1))

        return result

    def recv_have_list(self):
        self.remote_has = self.recv_oids("have", "done")
        self.conn.send_packet("NAK")

    def send_objects(self):
        revs = list(self.wanted) + [f"^{oid}" for oid in self.remote_has]
        self.send_packet_objects(revs)
