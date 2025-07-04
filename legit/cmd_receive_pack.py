from legit.cmd_base import Base
from legit.recv_objects import RecvObjectsMixin
from legit.remote_agent import RemoteAgentMixin
from legit.fast_forward import FastForwardMixin


class ReceivePack(FastForwardMixin, RecvObjectsMixin, RemoteAgentMixin, Base):
    CAPABILITIES = ["no-thin", "report-status", "delete-refs"]

    def run(self) -> None:
        self.accept_client("receive-pack", self.CAPABILITIES)

        self.send_references()
        self.recv_update_requests()
        self.recv_objects()
        self.update_refs()

        self.exit(0)

    def recv_update_requests(self) -> None:
        self.requests = {}

        for line in self.conn.recv_until(None):
            old_oid, new_oid, ref = line.split()
            self.requests[ref] = [self.zero_to_none(oid) for oid in (old_oid, new_oid)]

    def zero_to_none(self, oid) -> None:
        if oid == self.ZERO_OID:
            return None
        return oid

    def recv_objects(self) -> None:
        self.unpack_error = None
        unpack_limit = self.repo.config.get(["receive", "unpackLimit"])
        try:
            if any(vals and vals[-1] for vals in self.requests.values()):
                self.recv_packed_objects(unpack_limit)

            self.report_status("unpack ok")
        except Exception as e:
            self.unpack_error = e
            self.report_status(f"unpack {e}")

    def report_status(self, line) -> None:
        if self.conn.capable("report-status"):
            self.conn.send_packet(line)

    def update_refs(self) -> None:
        for ref, (old, new) in self.requests.items():
            self.update_ref(ref, old, new)
        self.report_status(None)

    def update_ref(self, ref, old, new):
        if self.unpack_error:
            return self.report_status(f"ng {ref} unpacker error")
            
        self.validate_update(ref, old, new)

        try:
            self.repo.refs.compare_and_swap(ref, old, new)
            self.report_status(f"ok {ref}")
        except Exception as e:
            self.report_status(f"ng {ref} {e}")

    def validate_update(self, ref, old, new):
        if self.repo.config.get(["receive", "denyDeletes"]):
            if not new:
                raise Exception("deletion prohibited")

        if self.repo.config.get(["receive", "denyNonFastForwards"]):
            if self.fast_forward_error(old, new):
                raise Exception("non-fast-forward")
    
        if not self.repo.config.get(["core", "bare"]) or self.repo.refs.current_ref().path != ref:
            return

        if not self.repo.config.get(["receive", "denyCurrentBranch"]):
            if new:
                raise Exception("branch is currently checked out")
        
        if not self.repo.config.get(["receive", "denyDeleteCurrent"]):
            if not new:
                raise Exception("deletion of the current branch prohibited")
        
