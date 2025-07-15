from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import MutableMapping, TextIO, Union, cast

from legit.cmd_base import Base

LABEL_WIDTH = 12

StatusKey = Union[str, tuple[int, ...]]

SHORT_STATUS: dict[str, str] = {
    "added": "A",
    "modified": "M",
    "deleted": "D",
}

LONG_STATUS: dict[StatusKey, str] = {
    "added": "new file:",
    "deleted": "deleted:",
    "modified": "modified:",
}

CONFLICT_LABEL_WIDTH: int = 17
CONFLICT_LONG_STATUS: dict[StatusKey, str] = {
    (1, 2, 3): "both modified:",
    (1, 2): "deleted by them:",
    (1, 3): "deleted by us:",
    (2, 3): "both added:",
    (2,): "added by us:",
    (3,): "added by them:",
}

UI_LABELS: dict[str, dict[StatusKey, str]] = {
    "normal": LONG_STATUS,
    "conflict": CONFLICT_LONG_STATUS,
}

UI_WIDTHS: dict[str, int] = {
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

    def print_branch_status(self) -> None:
        current = self.repo.refs.current_ref()

        if current.is_head():
            self.println(self.fmt("red", "Not currently on any branch"))
        else:
            self.println(f"On branch '{current.short_name()}'")

    def hint(self, msg: str) -> None:
        self.println(f"  ({msg})")

    def print_upstream_status(self) -> None:
        divergence = self.repo.divergence(self.repo.refs.current_ref())
        if divergence is None or divergence.upstream is None:
            return

        base = self.repo.refs.short_name(divergence.upstream)
        ahead = divergence.ahead
        behind = divergence.behind

        if ahead == 0 and behind == 0:
            self.println(f"Your branch is up to date with '{base}'.")
        elif behind == 0:
            self.println(f"Your branch is ahead of '{base}' by {self.commits(ahead)}.")
        elif ahead == 0:
            self.println(
                f"Your branch is behind '{base}' by {self.commits(behind)}, and can be fast-forwarded."
            )
        else:
            self.println(f"Your branch and '{base}' have diverged,")
            self.println(
                f"and have {ahead} and {behind} different commits each, respectively."
            )

        self.println("")

    def commits(self, n: int) -> str:
        if n == 1:
            return "commit"
        else:
            return f"{n} commits"

    def print_long_format(self) -> None:
        assert self.status_state is not None

        self.print_branch_status()
        self.print_upstream_status()
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
        changeset: MutableMapping[str, str] | defaultdict[str, list[int]],
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
            if label_set == "normal":
                key: StatusKey = cast(str, ty)
            else:
                key = tuple(cast(list[int], ty))

            status = labels[key].ljust(width, " ") if ty else ""
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
