from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from legit.blob import Blob
from legit.db_entry import DatabaseEntry
from legit.index import Entry

if TYPE_CHECKING:
    from legit.repository import Repository


class Inspector:
    def __init__(self, repo: Repository) -> None:
        self.repo: Repository = repo

    def compare_index_to_workspace(
        self, entry: Optional[Entry], stat: os.stat_result | None
    ) -> Optional[str]:
        if entry is None:
            return "untracked"

        if stat is None:
            return "deleted"

        if not entry.stat_match(stat):
            return "modified"

        if entry.times_match(stat):
            return None

        data = self.repo.workspace.read_file(entry.path)
        blob = Blob(data)
        oid = self.repo.database.hash_object(blob)

        if entry.oid != oid:
            return "modified"

        return None

    def compare_tree_to_index(
        self, item: Optional[DatabaseEntry], entry: Optional[Entry]
    ) -> Optional[str]:
        if item is None and entry is None:
            return None

        if item is None:
            return "added"

        if entry is None:
            return "deleted"

        if entry.mode() != item.mode or entry.oid != item.oid:
            return "modified"

        return None

    def _is_trackable_file(self, path: Path, stat: Optional[os.stat_result]) -> bool:
        if stat is None:
            return False

        if self._is_file(stat):
            return not self.repo.index.is_tracked_file(path)

        if not self._is_dir(stat):
            return False

        items = self.repo.workspace.list_dir(str(path))
        files = [(k, v) for k, v in items.items() if self._is_file(v)]
        dirs = [(k, v) for k, v in items.items() if self._is_dir(v)]

        for x in (files, dirs):
            for child_path, child_stat in x:
                if self._is_trackable_file(child_path, child_stat):
                    return True

        return False

    def _is_file(self, stat_result: os.stat_result) -> bool:
        return stat.S_ISREG(stat_result.st_mode)

    def _is_dir(self, stat_result: os.stat_result) -> bool:
        return stat.S_ISDIR(stat_result.st_mode)
