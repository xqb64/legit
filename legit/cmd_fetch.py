from legit.cmd_base import Base
from legit.remotes import Remotes, Refspec
from legit.rev_list import RevList
from legit.pack import SIGNATURE
from legit.remote_client import RemoteClientMixin
from legit.recv_objects import RecvObjectsMixin
from legit.fast_forward import FastForwardMixin


class Fetch(RemoteClientMixin, RecvObjectsMixin, FastForwardMixin, Base):
    UPLOAD_PACK = "git-upload-pack"

    def define_options(self) -> None:
        self.options = {"force": False, "uploader": ""}
        positional = []
        args_iter = iter(self.args)
        for arg in args_iter:
            if arg in ("--force", "-f"):
                self.options["force"] = True
            elif arg.startswith("--upload-pack="):
                self.options["uploader"] = arg.split('=', 1)[1]
            else:
                positional.append(arg)
        self.args = positional

    def run(self) -> None:
        self.define_options()
        self.configure()

        self.start_agent("fetch", self.uploader, self.fetch_url)

        self.recv_references()
        self.send_want_list()
        self.send_have_list()
        self.recv_objects()
        self.update_remote_refs()
            
        self.exit(0 if not self.errors else 1)

    def configure(self) -> None:
        try:
            name = self.args[0]
        except IndexError:
            name = Remotes.DEFAULT_REMOTE

        remote = self.repo.remotes.get(name)

        if remote is not None:
            self.fetch_url = remote.fetch_url
        else:
            self.fetch_url = self.args[0]

        self.uploader = self.options["uploader"] or (remote.uploader if remote is not None else None) or Fetch.UPLOAD_PACK
        self.fetch_specs = self.args[1:] if len(self.args) > 1 else remote.fetch_specs if remote is not None else None

    def send_want_list(self):
        self.targets = Refspec.expand(self.fetch_specs, self.remote_refs.keys())
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
            self.conn.send_packet(f"want {oid}")

        self.conn.send_packet(None)

        if not wanted:
            self.exit(0)


    def send_have_list(self):
        options = {"all": True, "missing": True}
        rev_list = RevList(self.repo, [], options)

        for commit in rev_list.each():
            self.conn.send_packet(f"have {commit.oid}")
        self.conn.send_packet("done")

        for _ in self.conn.recv_until(SIGNATURE):
            pass

    def recv_objects(self):
        unpack_limit = self.repo.config.get(["fetch", "unpackLimit"])
        self.recv_packed_objects(unpack_limit, SIGNATURE)

    def update_remote_refs(self):
        self.stderr.write("From {self.fetch_url}\n")

        self.errors = {}

        for target, oid in self.local_refs.items():
            self.attempt_ref_update(target, oid)

    def attempt_ref_update(self, target, old_oid):
        source, forced = self.targets[target]

        new_oid = self.remote_refs[source]
        ref_names = (source, target)
        ff_error = self.fast_forward_error(old_oid, new_oid)
        
        # FIXME
        error = None

        if self.options["force"] or forced or ff_error is None:
            self.repo.refs.update_ref(target, new_oid)
        else:
            error = self.errors[target] = ff_error

        self.report_ref_update(ref_names, error, old_oid, new_oid, ff_error is None)



