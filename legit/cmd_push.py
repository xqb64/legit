import re

from legit.cmd_base import Base
from legit.fast_forward import FastForwardMixin
from legit.remote_client import RemoteClientMixin
from legit.send_objects import SendObjectsMixin
from legit.remotes import Remotes, Refspec
from legit.revision import Revision

import logging

log = logging.getLogger(__name__)

logging.disable()


class Push(FastForwardMixin, RemoteClientMixin, SendObjectsMixin, Base):
    CAPABILITIES = ["report-status"]
    RECEIVE_PACK = "git-receive-pack"

    UNPACK_LINE = re.compile(r"^unpack (.+)$".encode())
    UPDATE_LINE = re.compile(r"^(ok|ng) (\S+)(.*)$".encode())

    def define_options(self) -> None:
        self.options = {"force": False}
        positional = []
        args_iter = iter(self.args)
        for arg in args_iter:
            if arg in ("-f", "--force"):
                self.options["force"] = True
            elif arg.startswith("--receive-pack="):
                self.options["receiver"] = arg.split("=", 1)[1]
            else:
                positional.append(arg)
        self.args = positional

    def run(self) -> None:
        self.define_options()
        self.configure()

        log.debug("push started, starting agent")
        self.start_agent("push", self.receiver, self.push_url, self.CAPABILITIES)

        log.debug("receiving references")
        self.recv_references()
        log.debug("recvd references")

        log.debug("sending update requests")
        self.send_update_requests()
        log.debug("sent update requests")

        log.debug("sending objects")
        self.send_objects()
        log.debug("sent objects")

        self.conn.output.close()

        log.debug("printing summary")
        self.print_summary()
        log.debug("printed summary")

        log.debug("receiving report status")
        self.recv_report_status()
        log.debug("received report status")

        self.exit(0 if not self.errors else 1)

    def configure(self) -> None:
        current_branch = self.repo.refs.current_ref().short_name()
        branch_remote = self.repo.config.get(["branch", current_branch, "remote"])
        branch_merge = self.repo.config.get(["branch", current_branch, "merge"])

        try:
            name = self.args[0]
        except IndexError:
            name = branch_remote or Remotes.DEFAULT_REMOTE

        remote = self.repo.remotes.get(name)

        self.push_url = remote.push_url if remote is not None else self.args[0]
        self.fetch_specs = remote.fetch_specs if remote is not None else []
        self.receiver = (
            self.options.get("receiver") or remote.receiver or self.RECEIVE_PACK
        )

        if len(self.args) > 1:
            self.push_specs = self.args[1:]
        elif branch_merge:
            spec = Refspec(current_branch, branch_merge, False)
            self.push_specs = [str(spec)]
        else:
            self.push_specs = remote.push_specs if remote is not None else None

    def send_update_requests(self) -> None:
        self.updates = {}
        self.errors = []

        local_refs = list(sorted(ref.path for ref in self.repo.refs.list_all_refs()))
        targets = Refspec.expand(self.push_specs, local_refs)

        for target, (source, forced) in targets.items():
            self.select_update(target, source, forced)

        log.debug(f"About to send updates. self.updates contains: {self.updates}")

        for ref, values in self.updates.items():
            *_, old, new = values
            self.send_update(ref, old, new)

        self.conn.send_packet(None)
        self.conn.output.flush()

    def select_update(self, target, source, forced) -> None:
        if not source:
            return self.select_deletion(target)

        old_oid = self.remote_refs.get(target)
        new_oid = Revision(self.repo, source).resolve()

        if old_oid == new_oid:
            return

        ff_error = self.fast_forward_error(old_oid, new_oid)

        if self.options["force"] or forced or ff_error is None:
            self.updates[target] = [source, ff_error, old_oid, new_oid]
        else:
            self.errors.append([[source, target], ff_error])

    def select_deletion(self, target) -> None:
        if self.conn.capable("delete-refs"):
            self.updates[target] = [None, None, self.remote_refs[target], None]
        else:
            self.errors.append(
                [[None, target], "remote does not support deleting refs"]
            )

    def send_update(self, ref, old_oid, new_oid) -> None:
        old_oid = self.none_to_zero(old_oid)
        new_oid = self.none_to_zero(new_oid)

        self.conn.send_packet(f"{old_oid} {new_oid} {ref}".encode())

    def none_to_zero(self, oid) -> str:
        if oid is None:
            return self.ZERO_OID.decode()
        return oid

    def send_objects(self) -> None:
        revs = [
            vals[-1] for vals in self.updates.values() if vals and vals[-1] is not None
        ]
        if not revs:
            return

        revs += [f"^{oid}" for oid in self.remote_refs.values()]

        self.send_packet_objects(revs)

    def print_summary(self) -> None:
        log.debug(f"About to print summary. self.updates contains: {self.updates}")
        if not self.updates and not self.errors:
            self.stderr.write("Everything up-to-date\n")
        else:
            self.stderr.write(f"To {self.push_url}\n")
            for ref_names, error in self.errors:
                self.report_ref_update(ref_names, error)

    def recv_report_status(self) -> None:
        if not self.conn.capable("report-status") or not self.updates:
            return

        unpack_line = self.conn.recv_packet()
        if unpack_line:
            unpack_match = self.UNPACK_LINE.match(unpack_line)
            if unpack_match:
                unpack_result = unpack_match.group(1)
                if unpack_result != b"ok":
                    self.stderr.write(f"error: remote unpack failed: {unpack_result}\n")
            else:
                self.handle_status(unpack_line)

        for line in self.conn.recv_until(None):
            if line:
                self.handle_status(line)

    def handle_status(self, line) -> None:
        m = self.UPDATE_LINE.match(line)
        if not m:
            return

        status = m.group(1)
        ref = m.group(2).decode()

        error = None if status == b"ok" else m.group(3).strip().decode()

        if error:
            self.errors.append([ref, error])

        self.report_update(ref, error)

        targets = Refspec.expand(self.fetch_specs, [ref])

        for local_ref, (remote_ref, _) in targets.items():
            new_oid = self.updates[remote_ref][-1]
            if not error:
                self.repo.refs.update_ref(local_ref, new_oid)

    def report_update(self, target, error):
        source, ff_error, old_oid, new_oid = self.updates[target]
        ref_names = [source, target]
        self.report_ref_update(ref_names, error, old_oid, new_oid, ff_error is None)
