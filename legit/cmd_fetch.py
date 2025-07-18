from __future__ import annotations

from typing import Optional, cast

from legit.cmd_base import Base
from legit.fast_forward import FastForwardMixin
from legit.pack import SIGNATURE
from legit.recv_objects import RecvObjectsMixin
from legit.remote_client import RemoteClientMixin
from legit.remotes import Refspec, Remotes
from legit.rev_list import RevList


class Fetch(RemoteClientMixin, RecvObjectsMixin, FastForwardMixin, Base):
    UPLOAD_PACK: str = "git-upload-pack"
    CAPABILITIES: list[str] = ["ofs-delta"]

    def define_options(self) -> None:
        self.options: dict[str, bool | str] = {"force": False, "uploader": ""}
        positional = []
        args_iter = iter(self.args)
        for arg in args_iter:
            if arg in ("--force", "-f"):
                self.options["force"] = True
            elif arg.startswith("--upload-pack="):
                self.options["uploader"] = arg.split("=", 1)[1]
            else:
                positional.append(arg)
        self.args = positional

    def run(self) -> None:
        self.define_options()
        self.configure()

        self.start_agent("fetch", self.uploader, self.fetch_url, self.CAPABILITIES)
        self.recv_references()
        self.send_want_list()
        self.send_have_list()
        self.recv_objects()
        self.update_remote_refs()

        self.exit(0 if not self.errors else 1)

    def configure(self) -> None:
        current_branch = self.repo.refs.current_ref().short_name()
        branch_remote = cast(
            str, self.repo.config.get(["branch", current_branch, "remote"])
        )

        try:
            name = self.args[0]
        except IndexError:
            name = branch_remote or Remotes.DEFAULT_REMOTE

        remote = self.repo.remotes.get(name)

        if remote is not None:
            self.fetch_url = cast(str, remote.fetch_url)
        else:
            self.fetch_url = self.args[0]

        self.uploader = (
            cast(str, self.options["uploader"])
            or (cast(str, remote.uploader) if remote is not None else None)
            or Fetch.UPLOAD_PACK
        )
        self.fetch_specs: list[str] = cast(
            list[str],
            (
                self.args[1:]
                if len(self.args) > 1
                else remote.fetch_specs
                if remote is not None
                else None
            ),
        )

    def send_want_list(self) -> None:
        self.targets = Refspec.expand(self.fetch_specs, list(self.remote_refs.keys()))
        wanted = set()

        self.local_refs = {}

        for target, (source, _) in self.targets.items():
            local_oid = self.repo.refs.read_ref(target)
            remote_oid = self.remote_refs[source]

            if local_oid == remote_oid:
                continue

            self.local_refs[target] = local_oid
            wanted.add(remote_oid)

        for oid in wanted:
            self.conn.send_packet(f"want {oid}".encode())

        self.conn.send_packet(None)

        if not wanted:
            self.exit(0)

    def send_have_list(self) -> None:
        options = {"all": True, "missing": True}
        rev_list = RevList(self.repo, [], options)

        for commit, _ in rev_list.each():
            self.conn.send_packet(f"have {commit.oid}".encode())

        self.conn.send_packet(b"done")
        for _ in self.conn.recv_until(SIGNATURE):
            pass

    def recv_objects(self) -> None:
        unpack_limit = cast(int, self.repo.config.get(["fetch", "unpackLimit"]))
        self.recv_packed_objects(unpack_limit, SIGNATURE)

    def update_remote_refs(self) -> None:
        self.eprintln(f"From {self.fetch_url}")

        self.errors: dict[str, Optional[str]] = {}

        for target, oid in self.local_refs.items():
            self.attempt_ref_update(target, cast(str, oid))

    def attempt_ref_update(self, target: str, old_oid: str) -> None:
        source, forced = self.targets[target]

        new_oid = self.remote_refs[source]
        ref_names = (source, target)
        ff_error = self.fast_forward_error(old_oid, new_oid)

        error = ""

        if self.options["force"] or forced or ff_error is None:
            self.repo.refs.update_ref(target, new_oid)
        else:
            error = self.errors[target] = ff_error

        self.report_ref_update(ref_names, error, old_oid, new_oid, ff_error is None)
