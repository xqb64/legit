from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Optional, cast

from legit.blob import Blob
from legit.cmd_base import Base
from legit.db_entry import DatabaseEntry
from legit.index import Entry
from legit.print_diff import PrintDiffMixin, Target
from legit.status import Status


class Diff(PrintDiffMixin, Base):
    NULL_OID = "0" * 40

    def run(self) -> None:
        self.patch = True
        self.define_print_diff_options()

        if any(x in self.args for x in ("--cached", "--staged")):
            self.cached = True
        else:
            self.cached = False

        self.stage: Optional[int] = None
        if any(x in self.args for x in ("-1", "--base")):
            self.stage = 1
        elif any(x in self.args for x in ("-2", "--ours")):
            self.stage = 2
        elif any(x in self.args for x in ("-3", "--theirs")):
            self.stage = 3

        self.repo.index.load()
        self.status_state: Status = self.repo.status()

        self.setup_pager()

        if self.cached:
            self.diff_head_index()
        else:
            self.diff_index_workspace()

        self.exit(0)

    def diff_head_index(self) -> None:
        if not self.patch:
            return

        for path, state in self.status_state.index_changes.items():
            if state == "modified":
                self.print_diff(self.from_head(Path(path)), self.from_index(Path(path)))
            elif state == "added":
                self.print_diff(
                    self.from_nothing(Path(path)), self.from_index(Path(path))
                )
            elif state == "deleted":
                self.print_diff(
                    self.from_head(Path(path)), self.from_nothing(Path(path))
                )

    def diff_index_workspace(self) -> None:
        if not self.patch:
            return

        paths: dict[str, str | list[int]] = {
            **self.status_state.conflicts,
            **self.status_state.workspace_changes,
        }

        for path, state in paths.items():
            if path in self.status_state.conflicts:
                self.print_conflict_diff(path)
            else:
                self.print_workspace_diff(path)

    def print_conflict_diff(self, path: str) -> None:
        targets = [self.from_index(Path(path), stage) for stage in range(4)]
        left, right = targets[2], targets[3]

        if self.stage is not None:
            self.println(f"* Unmerged path {path}")
            self.print_diff(targets[self.stage], self.from_file(Path(path)))
        elif left is not None and right is not None:
            self.print_combined_diff([left, right], self.from_file(Path(path)))
        else:
            self.println(f"* Unmerged path {path}")

    def print_workspace_diff(self, path: str) -> None:
        state = self.status_state.workspace_changes[path]
        if state == "modified":
            self.print_diff(self.from_index(Path(path)), self.from_file(Path(path)))
        elif state == "deleted":
            self.print_diff(self.from_index(Path(path)), self.from_nothing(Path(path)))

    def from_head(self, path: Path) -> "Target":
        entry = cast(DatabaseEntry, self.status_state.head_tree[path])
        blob = cast(Blob, self.repo.database.load(entry.oid))
        return Target(path, entry.oid, oct(entry.mode)[2:], blob.data.decode("utf-8"))

    def from_index(self, path: Path, stage: int = 0) -> "Target | None":
        entry = self.repo.index.entry_for_path(path, stage)
        if entry is None:
            return None

        blob = self.repo.database.load(entry.oid)
        assert isinstance(blob, Blob)
        return Target(path, entry.oid, oct(entry.mode())[2:], blob.data.decode("utf-8"))

    def from_file(self, path: Path) -> "Target":
        blob = Blob(self.repo.workspace.read_file(path))
        oid = self.repo.database.hash_object(blob)
        mode = Entry.mode_for_stat(self.status_state.stats[path])
        return Target(path, oid, oct(mode)[2:], blob.data.decode("utf-8"))

    def from_nothing(self, path: Path) -> "Target":
        return Target(path, Diff.NULL_OID, None, "")
