from collections import defaultdict
import os
import stat
from typing import TextIO, MutableMapping, cast
from pathlib import Path

from legit import index
from legit.blob import Blob
from legit.cmd_base import Base
from legit.commit import Commit
from legit.index import Entry
from legit.repository import Repository
from legit.tree import DatabaseEntry, Tree
from legit.status import Status
from legit.cmd_color import Color


LABEL_WIDTH = 12

SHORT_STATUS: MutableMapping[str, str] = {
    "added": "A",
    "modified": "M",
    "deleted": "D",
}

LONG_STATUS: MutableMapping[str, str] = {
    "added": "new file:",
    "deleted": "deleted:",
    "modified": "modified:",
}

CONFLICT_LABEL_WIDTH: int = 17
CONFLICT_LONG_STATUS = {
    (1, 2, 3): "both modified:",
    (1, 2): "deleted by them:",
    (1, 3): "deleted by us:",
    (2, 3): "both added:",
    (2,): "added by us:",
    (3,): "added by them:",
}

UI_LABELS = {
    "normal": LONG_STATUS,
    "conflict": CONFLICT_LONG_STATUS,
}

UI_WIDTHS = {
    "normal": LABEL_WIDTH,
    "conflict": CONFLICT_LABEL_WIDTH,
}


CONFLICT_SHORT_STATUS = {
    (1, 2, 3): "UU",
    (1, 2): "UD",
    (1, 3): "DU",
    (2, 3): "AA",
    (2,): "AU",
    (3,): "UA",
}


class StatusCmd(Base):
    def __init__(
        self,
        _dir: Path,
        env: MutableMapping[str, str],
        args: list[str],
        stdin: TextIO,
        stdout: TextIO,
        stderr: TextIO,
    ) -> None:
        super().__init__(_dir, env, args, stdin, stdout, stderr)
        self.repo = Repository(self.dir / ".git")
        self.status_state: Status | None = None

    def run(self) -> None:
        self.repo.index.load_for_update()
        self.status_state = self.repo.status()
        self.repo.index.write_updates()

        self.print_results()

        self.exit(0)

    def print_results(self) -> None:
        try:
            fmt = self.args[0]
        except IndexError:
            fmt = None

        if fmt == "--porcelain":
            self.print_porcelain_format()
        else:
            self.print_long_format()

    def print_pending_commit_status(self) -> None:
        match self.repo.pending_commit().merge_type():
            case c if c == "merge":
                if not self.status_state.conflicts:
                    self.println("All conflicts fixed but you are still merging.")
                    self.hint("use 'legit commit' to conclude merge")
                else:
                    self.println("You have unmerged paths.")
                    self.hint("fix conflicts and run 'legit commit'")
                    self.hint("use 'legit merge --abort' to abort the merge")
                self.println("")
            case c if c == "cherry_pick":
                self.print_pending_type("cherry_pick")
            case c if c == "revert":
                self.print_pending_type("revert")

    def print_pending_type(self, ty: str) -> None:
        oid = self.repo.pending_commit().merge_oid(ty)
        short = self.repo.database.short_oid(oid)

        op = ty.replace("_", "-")

        self.println(f"You are currently {op}ing commit {short}.")

        if not self.status_state.conflicts:
            self.hint(f"all conflicts fixed: run 'legit {op} --continue'")
        else:
            self.hint(f"fix conflicts and run 'legit {op} --continue")

        self.hint(f"use 'legit {op} --abort' to cancel the {op} operation")

        self.println("")

    def hint(self, msg: str) -> None:
        self.println(f"  ({msg})")

    def print_long_format(self) -> None:
        assert self.status_state is not None

        self.print_branch_status()
        self.print_pending_commit_status()

        self.print_changes(
            "Changes to be committed", self.status_state.index_changes, "green"
        )
        self.print_changes(
            "Unmerged paths", self.status_state.conflicts, "red", "conflict"
        )
        self.print_changes(
            "Changes not staged for commit", self.status_state.workspace_changes, "red"
        )
        self.print_changes(
            "Untracked files",
            {p: "" for p in sorted(self.status_state.untracked)},
            "red",
        )

        self.print_commit_status()

    def print_changes(
        self,
        message: str,
        changeset: MutableMapping[str, str],
        color: str,
        label_set: str = "normal",
    ) -> None:
        if not changeset:
            return

        labels = UI_LABELS[label_set]
        width = UI_WIDTHS[label_set]

        self.println(message)
        self.println("")

        for path, ty in changeset.items():
            status = labels[ty].ljust(width, " ") if ty else ""
            self.println("\t" + self.fmt(color, f"{status}{path}"))

        self.println("")

    def print_commit_status(self) -> None:
        assert self.status_state is not None
        if self.status_state.index_changes:
            return

        if self.status_state.workspace_changes:
            self.println("no changes added to commit\n")
        elif self.status_state.untracked:
            self.println("nothing added to commit but untracked files present\n")
        else:
            self.println("nothing to commit, working tree clean\n")

    def print_porcelain_format(self) -> None:
        assert self.status_state is not None
        for path in sorted(self.status_state.changed):
            status = self.status_for_path(path)
            self.println(f"{status} {path}")

        for path in sorted(self.status_state.untracked):
            self.println(f"?? {path}")

    def status_for_path(self, path: str) -> str:
        assert self.status_state is not None
        if path in self.status_state.conflicts:
            return CONFLICT_SHORT_STATUS[
                tuple(sorted(self.status_state.conflicts[path]))
            ]
        else:
            left = SHORT_STATUS.get(
                cast(str, self.status_state.index_changes.get(path)), " "
            )
            right = SHORT_STATUS.get(
                cast(str, self.status_state.workspace_changes.get(path)), " "
            )
            return left + right
