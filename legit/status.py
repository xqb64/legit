from collections import defaultdict
import os
import stat
from pathlib import Path
from typing import (
    MutableMapping,
    TYPE_CHECKING,
    Optional,
)

if TYPE_CHECKING:
    from legit.repository import Repository
else:
    Repository = None

from legit.tree import DatabaseEntry
from legit.commit import Commit
from legit.tree import Tree
from legit.blob import Blob
from legit.index import Entry
from legit.inspector import Inspector


class Status:
    def __init__(self, repo: Repository, commit_oid: Optional[str] = None) -> None:
        self.inspector: Inspector = Inspector(repo)
        self.repo = repo
        self.stats: MutableMapping[Path, os.stat_result] = {}
        self.index_changes: MutableMapping[str, str] = {}
        self.workspace_changes: MutableMapping[str, str] = {}
        self.changed: set[str] = set()
        self.untracked: set[str] = set()
        self.conflicts = defaultdict(list)

        if commit_oid is None:
            commit_oid = self.repo.refs.read_head()

        self.head_tree = self.repo.database.load_tree_list(commit_oid)

        self.scan_workspace()
        self.check_index_entries()
        self.collect_deleted_head_files()


    def collect_deleted_head_files(self) -> None:
        for path in self.head_tree.keys():
            if not self.repo.index.is_tracked_file(path):
                self.record_change(path, self.index_changes, "deleted")

    def read_tree(self, tree_oid: str, pathname: str ='') -> None:
        tree = self.repo.database.load(tree_oid)
        assert isinstance(tree, Tree)

        for name, entry in tree.entries.items():
            path = Path(pathname) / name
            assert isinstance(entry, DatabaseEntry)
            if entry.is_tree():
                self.read_tree(entry.oid, str(path))
            else:
                self.head_tree[path] = entry

    def check_index_entries(self) -> None:
        for name, entry in self.repo.index.entries.items():
            if entry.stage == 0:
                self.check_index_against_workspace(entry)
                self.check_index_against_head_tree(entry)
            else:
                self.changed.add(str(entry.path))
                self.conflicts[str(entry.path)].append(entry.stage)

    def check_index_against_workspace(self, entry: Entry) -> None:
        """
        Compares an index entry with the corresponding file in the workspace
        to detect unstaged changes (modified, deleted).
        """
        # Attempt to get the file's status from our scan of the workspace.
        stat_result = self.stats.get(entry.path)

        status = self.inspector.compare_index_to_workspace(entry, stat_result)

        if status is not None:
            self.record_change(entry.path, self.workspace_changes, status)
        else:
            assert stat_result is not None
            self.repo.index.update_entry_stat(entry, stat_result)

    def check_index_against_head_tree(self, entry: Entry) -> None:
        item = self.head_tree.get(entry.path, None)
        status = self.inspector.compare_tree_to_index(item, entry)

        if status is not None:
            self.record_change(entry.path, self.index_changes, status)
            
    def record_change(self, path: Path, structure: MutableMapping[str, str], ty: str) -> None:
        self.changed.add(str(path))
        structure[str(path)] = ty

    def scan_workspace(self, prefix: str = '') -> None:
        for path, stat in self.repo.workspace.list_dir(prefix).items():
            if self.repo.index.is_tracked(path):
                if self.inspector._is_dir(stat):
                    self.scan_workspace(str(path))
                elif self.inspector._is_file(stat):
                    self.stats[path] = stat
            elif self.inspector._is_trackable_file(path, stat):
                if self.inspector._is_dir(stat):
                    self.untracked.add(f"{path}{os.sep}")
                else:
                    self.untracked.add(str(path))

    def detect_workspace_changes(self) -> None:
        for path, entry in self.repo.index.entries.items():
            self.check_index_entry(entry)

    def check_index_entry(self, entry: Entry) -> None:
        stat = self.stats.get(entry.path, None)
        if stat is None:
            self.record_change(entry.path, self.workspace_changes, "deleted")
            return

        if not entry.stat_match(stat):
            self.record_change(entry.path, self.workspace_changes, "modified")
            return
        
        if entry.times_match(stat):
            return
        
        data = self.repo.workspace.read_file(entry.path)
        blob = Blob(data)
        oid = self.repo.database.hash_object(blob)

        if entry.oid == oid:
            self.repo.index.update_entry_stat(entry, stat)
        else:
            self.record_change(entry.path, self.workspace_changes, "modified")


