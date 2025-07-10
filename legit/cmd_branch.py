from __future__ import annotations

import enum
from typing import Union, cast

from legit.cmd_base import Base
from legit.commit import Commit
from legit.fast_forward import FastForwardMixin
from legit.refs import Refs
from legit.remotes import Remotes
from legit.revision import Revision


class Upstream(enum.Enum):
    UNSET = enum.auto()


class Branch(FastForwardMixin, Base):
    def define_options(self) -> None:
        self.options: dict[str, int | bool | Union[str, Upstream]] = {
            "verbose": 0,
            "delete": False,
            "force": False,
            "all": False,
            "remotes": False,
            "upstream": "",
            "track": False,
        }
        args_iter = iter(self.args)
        positional = []
        for arg in args_iter:
            if arg in ("-v", "--verbose"):
                assert isinstance(self.options["verbose"], int)
                self.options["verbose"] += 1
            elif arg == "-vv":
                assert isinstance(self.options["verbose"], int)
                self.options["verbose"] += 2
            elif arg == "-D":
                self.options["delete"] = True
                self.options["force"] = True
            elif arg in ("-d", "--delete"):
                self.options["delete"] = True
            elif arg in ("-f", "--force"):
                self.options["force"] = True
            elif arg in ("-a", "--all"):
                self.options["all"] = True
            elif arg in ("-r", "--remotes"):
                self.options["remotes"] = True
            elif arg == "--set-upstream-to":
                self.options["upstream"] = next(args_iter)
            elif arg.startswith("--set-upstream-to="):
                self.options["upstream"] = arg.split("=", 1)[1]
            elif arg == "-u":
                self.options["upstream"] = next(args_iter)
            elif arg in ("-t", "--track"):
                self.options["track"] = True
            elif arg == "--unset-upstream":
                self.options["upstream"] = Upstream.UNSET
            else:
                positional.append(arg)

        self.args = positional

    def run(self) -> None:
        self.define_options()

        if self.options["upstream"]:
            self.set_upstream_branch()
        elif self.options["delete"]:
            self.delete_branches()
        elif not self.args:
            self.list_branches()
        else:
            self.create_branch()

        self.exit(0)

    def set_upstream(self, branch_name: str, upstream: str) -> None:
        try:
            upstream = self.repo.refs.long_name(upstream)
            remote, ref = self.repo.remotes.set_upstream(branch_name, upstream)

            base = self.repo.refs.short_name(ref)

            self.println(
                f"Branch '{branch_name}' set up to track remote branch '{base}' from '{remote}'."
            )
        except Refs.InvalidBranch as e:
            self.stderr.write(f"error: {e}\n")
            self.exit(1)
        except Remotes.InvalidBranch as e:
            self.stderr.write(f"fatal: {e}\n")
            self.exit(128)

    def set_upstream_branch(self) -> None:
        try:
            branch_name = self.args[0]
        except IndexError:
            branch_name = self.repo.refs.current_ref().short_name()

        if self.options["upstream"] == Upstream.UNSET:
            self.repo.remotes.unset_upstream(branch_name)
        else:
            self.set_upstream(branch_name, cast(str, self.options["upstream"]))

    def list_branches(self) -> None:
        current = self.repo.refs.current_ref()
        branches = sorted(self.branch_refs(), key=lambda x: x.path)
        max_width = max((len(b.short_name()) for b in branches), default=0)

        self.setup_pager()

        for ref in branches:
            info = self.format_ref(ref, current)
            info += self.extended_branch_info(ref, max_width)
            self.println(info)

    def branch_refs(self) -> list[Refs.SymRef]:
        branches = self.repo.refs.list_branches()
        remotes = self.repo.refs.list_remotes()

        if self.options["all"]:
            return branches + remotes

        if self.options["remotes"]:
            return remotes

        return branches

    def format_ref(self, ref: Refs.SymRef, current: Refs.SymRef) -> str:
        if ref == current:
            return f"* {self.fmt('green', ref.short_name())}"
        elif ref.is_remote():
            return f"  {self.fmt('red', ref.short_name())}"
        return f"  {ref.short_name()}"

    def extended_branch_info(self, ref: Refs.SymRef, max_width: int) -> str:
        if not cast(int, self.options["verbose"]) > 0:
            return ""

        oid = ref.read_oid()
        assert oid is not None

        commit = cast(Commit, self.repo.database.load(oid))
        short = self.repo.database.short_oid(commit.oid)
        space = " " * (max_width - len(ref.short_name()))
        upstream = self.upstream_info(ref) or ""
        return f"{space} {short}{upstream} {commit.title_line()}"

    def upstream_info(self, ref: Refs.SymRef) -> str | None:
        divergence = self.repo.divergence(ref)
        if divergence.upstream is None:
            return None

        ahead = divergence.ahead
        behind = divergence.behind

        info = []

        if cast(int, self.options["verbose"]) > 1:
            info.append(
                self.fmt("blue", self.repo.refs.short_name(divergence.upstream))
            )

        if ahead > 0:
            info.append(f"ahead {ahead}")

        if behind > 0:
            info.append(f"behind {behind}")

        if not info:
            return ""

        return f" [{', '.join(info)}]"

    def create_branch(self) -> None:
        try:
            branch_name = self.args[0]
        except IndexError:
            branch_name = None
        try:
            start_point = self.args[1]
        except IndexError:
            start_point = None

        if start_point is not None:
            revision = Revision(self.repo, start_point)
            try:
                start_oid = revision.resolve(Revision.COMMIT)
            except Revision.InvalidObject as e:
                start_oid = None
                for err in revision.errors:
                    self.stderr.write(f"error: {err.msg}\n")
                    for line in err.hint:
                        self.stderr.write(f"hint: {line}\n")
                self.stderr.write(f"fatal: {e}\n")
                self.exit(128)
        else:
            start_oid = self.repo.refs.read_head()

        assert branch_name is not None
        assert start_oid is not None

        try:
            self.repo.refs.create_branch(branch_name, start_oid)
            if self.options["track"]:
                self.set_upstream(branch_name, cast(str, start_point))
        except Refs.InvalidBranch as e:
            self.stderr.write(f"fatal: {e}\n")
            self.exit(128)

    def delete_branches(self) -> None:
        for branch_name in self.args:
            self.delete_branch(branch_name)

    def delete_branch(self, branch_name: str) -> None:
        if not self.options["force"]:
            self.check_merge_status(branch_name)

        try:
            oid = self.repo.refs.delete_branch(branch_name)
            short = self.repo.database.short_oid(oid)
            self.repo.remotes.unset_upstream(branch_name)

            self.println(f"Deleted branch '{branch_name}' (was {short}).")
        except Refs.InvalidBranch as e:
            self.stderr.write(f"error: {e}\n")
            self.exit(1)

    def check_merge_status(self, branch_name: str) -> None:
        upstream = self.repo.remotes.get_upstream(branch_name)
        head_oid = (
            self.repo.refs.read_ref(upstream)
            if upstream is not None
            else self.repo.refs.read_head()
        )
        branch_oid = self.repo.refs.read_ref(branch_name)

        if self.fast_forward_error(branch_oid, head_oid):
            self.stderr.write(
                f"error: The branch '{branch_name}' is not fully merged.\n"
            )
            self.exit(1)
