from __future__ import annotations

import os
import stat as _stat
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

from legit.blob import Blob
from legit.db_entry import DatabaseEntry
from legit.index import Entry
from legit.inspector import Inspector

if TYPE_CHECKING:
    from legit.repository import Repository


class Migration:
    class Conflict(Exception):
        pass

    MESSAGES: Dict[str, Tuple[str, str]] = {
        "stale_file": (
            "Your local changes to the following files would be overwritten by checkout:",
            "Please commit your changes or stash them before you switch branches.",
        ),
        "stale_directory": (
            "Updating the following directories would lose untracked files in them:",
            "",
        ),
        "untracked_overwritten": (
            "The following untracked working tree files would be overwritten by checkout:",
            "Please move or remove them before you switch branches.",
        ),
        "untracked_removed": (
            "The following untracked working tree files would be removed by checkout:",
            "Please move or remove them before you switch branches.",
        ),
    }

    def __init__(
        self,
        repo: Repository,
        tree_diff: dict[Path, list[DatabaseEntry | None]],
    ) -> None:
        self.repo: Repository = repo
        self.tree_diff: dict[Path, list[DatabaseEntry | None]] = tree_diff

        self.changes: Dict[str, List[Tuple[Path, Optional[DatabaseEntry]]]] = {
            k: [] for k in ("create", "update", "delete")
        }
        self.mkdirs: Set[Path] = set()
        self.rmdirs: Set[Path] = set()

        self.errors: List[str] = []
        self.inspector: Inspector = Inspector(repo)
        self.conflicts: Dict[str, Set[str]] = {
            "stale_file": set(),
            "stale_directory": set(),
            "untracked_overwritten": set(),
            "untracked_removed": set(),
        }

    def apply_changes(self) -> None:
        self.plan_changes()
        self.update_workspace()
        self.update_index()

    def blob_data(self, oid: str) -> bytes:
        blob = self.repo.database.load(oid)
        assert isinstance(blob, Blob)
        return blob.data

    def plan_changes(self) -> None:
        for path, (old_item, new_item) in self.tree_diff.items():
            self.check_for_conflict(path, old_item, new_item)
            self.record_change(path, old_item, new_item)

        self.collect_errors()

    @staticmethod
    def _ancestor_dirs(p: Path) -> List[Path]:
        dirs = [p]
        for parent in p.parents:
            if parent == Path("."):
                break
            dirs.append(parent)
        return dirs

    def record_change(
        self,
        path: Path,
        old_item: Optional[DatabaseEntry],
        new_item: Optional[DatabaseEntry],
    ) -> None:
        dir_chain = self._ancestor_dirs(path.parent)

        if old_item is None:
            self.mkdirs.update(dir_chain)
            action = "create"
        elif new_item is None:
            self.rmdirs.update(dir_chain)
            action = "delete"
        else:
            self.mkdirs.update(dir_chain)
            action = "update"

        self.changes[action].append((path, new_item))

    def check_for_conflict(
        self,
        path: Path,
        old_item: Optional[DatabaseEntry],
        new_item: Optional[DatabaseEntry],
    ) -> None:
        entry: Optional[Entry] = self.repo.index.entry_for_path(path)

        if self.index_differs_from_trees(entry, old_item, new_item):
            self.conflicts["stale_file"].add(str(path))
            return

        try:
            stat = self.repo.workspace.stat_file(path)
        except (FileNotFoundError, NotADirectoryError):
            stat = None

        conflict_type = self.get_error_type(stat, entry, new_item)

        if stat is None:
            parent = self.untracked_parent(path)
            if parent:
                self.conflicts[conflict_type].add(str(path if entry else parent))
        elif self._is_file(stat):
            changed = self.inspector.compare_index_to_workspace(entry, stat)
            if changed:
                self.conflicts[conflict_type].add(str(path))
        elif self._is_dir(stat):
            trackable = self.inspector._is_trackable_file(path, stat)
            if trackable:
                self.conflicts[conflict_type].add(str(path))

    @staticmethod
    def _is_file(stat_result: Optional[os.stat_result]) -> bool:
        return stat_result is not None and _stat.S_ISREG(stat_result.st_mode)

    @staticmethod
    def _is_dir(stat_result: Optional[os.stat_result]) -> bool:
        return stat_result is not None and _stat.S_ISDIR(stat_result.st_mode)

    def get_error_type(
        self,
        stat: Optional[os.stat_result],
        entry: Optional[Entry],
        item: Optional[DatabaseEntry],
    ) -> str:
        if entry is not None:
            return "stale_file"
        elif self._is_dir(stat):
            return "stale_directory"
        elif item:
            return "untracked_overwritten"
        else:
            return "untracked_removed"

    def index_differs_from_trees(
        self,
        entry: Optional[Entry],
        old_item: Optional[DatabaseEntry],
        new_item: Optional[DatabaseEntry],
    ) -> bool:
        return bool(self.inspector.compare_tree_to_index(old_item, entry)) and bool(
            self.inspector.compare_tree_to_index(new_item, entry)
        )

    def untracked_parent(self, path: Path) -> Path | None:
        for parent in path.parents:
            if str(parent) == ".":
                break

            parent_stat = self.repo.workspace.stat_file(parent)
            if not self._is_file(parent_stat):
                continue

            if self.inspector._is_trackable_file(parent, parent_stat):
                return parent
        return None

    def collect_errors(self) -> None:
        for kind, paths in sorted(self.conflicts.items()):
            if not paths:
                continue

            header, footer = self.MESSAGES[kind]
            body = "\n".join(f"\t{p}" for p in sorted(paths))
            self.errors.append("\n".join((header, body, footer)))

        if self.errors:
            raise self.Conflict

    def update_workspace(self) -> None:
        self.repo.workspace.apply_migration(self)

    def update_index(self) -> None:
        for path, _ in self.changes["delete"]:
            self.repo.index.remove(path)

        for action in ("create", "update"):
            for path, entry in self.changes[action]:
                stat = self.repo.workspace.stat_file(path)
                assert entry is not None
                assert stat is not None
                self.repo.index.add(path, entry.oid, stat)
