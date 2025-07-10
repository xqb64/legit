from legit.cmd_base import Base
from legit.recv_objects import RecvObjectsMixin
from legit.remote_agent import RemoteAgentMixin
from legit.fast_forward import FastForwardMixin

import logging


log = logging.getLogger(__name__)


class ReceivePack(FastForwardMixin, RecvObjectsMixin, RemoteAgentMixin, Base):
    CAPABILITIES = ["no-thin", "report-status", "delete-refs", "ofs-delta"]

    def run(self) -> None:
        log.debug("ReceivePack started. Accepting client...")
        self.accept_client("receive-pack", self.CAPABILITIES)

        log.debug("Sending references...")
        self.send_references()
        log.debug("Sent references.")

        log.debug("Receiving update requests...")
        self.recv_update_requests()
        log.debug("Received update requests.")

        log.debug("Receiving objects...")
        self.recv_objects()
        log.debug("Received objects.")

        log.debug("Updating refs...")
        self.update_refs()
        log.debug("Updated refs.")

        self.exit(0)

    def recv_update_requests(self) -> None:
        self.requests = {}

        for line in self.conn.recv_until(None):
            old_oid, new_oid, ref = line.split()
            ref = ref.decode()
            self.requests[ref] = [self.zero_to_none(oid) for oid in (old_oid, new_oid)]

    def zero_to_none(self, oid: bytes) -> None:
        if oid == self.ZERO_OID:
            return None
        return oid.decode()

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
            if line is None:
                self.conn.send_packet(None)
            else:
                self.conn.send_packet(line.encode())

    def update_refs(self) -> None:
        log.debug(f"update refs called, {self.requests=}")
        for ref, (old, new) in self.requests.items():
            self.update_ref(ref, old, new)
        self.report_status(None)

    def update_ref(self, ref, old, new):
        log.debug(f"{ref}, {type(ref)}")
        if self.unpack_error:
            return self.report_status(f"ng {ref} unpacker error")

        try:
            self.validate_update(ref, old, new)
            self.repo.refs.compare_and_swap(ref, old, new)
            self.report_status(f"ok {ref}")
        except Exception as e:
            self.report_status(f"ng {ref} {e}")

    def validate_update(self, ref, old_oid, new_oid):
        if self.repo.config.get(["receive", "denyDeletes"]):
            if not new_oid:
                raise Exception("deletion prohibited")

        if self.repo.config.get(["receive", "denyNonFastForwards"]):
            if self.fast_forward_error(old_oid, new_oid):
                raise Exception("non-fast-forward")

        if (
            self.repo.config.get(["core", "bare"]) is not False
            or self.repo.refs.current_ref().path != ref
        ):
            return

        if self.repo.config.get(["receive", "denyCurrentBranch"]) is not False:
            if new_oid:
                raise Exception("branch is currently checked out")

        if self.repo.config.get(["receive", "denyDeleteCurrent"]) is not False:
            if not new_oid:
                raise Exception("deletion of the current branch prohibited")
