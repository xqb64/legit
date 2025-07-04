import stat
import itertools
from pathlib import Path

from legit import inspector
from legit.cmd_base import Base
from legit.repository import Repository
from legit.inspector import Inspector


BOTH_CHANGED = "staged content different from both the file and the HEAD"
INDEX_CHANGED = "changes staged in the index"
WORKSPACE_CHANGED = "local modifications"


class Rm(Base):
    def run(self) -> None:
        self.define_options()
        self.repo.index.load_for_update()

        self.head_oid = self.repo.refs.read_head()
        self.inspector = Inspector(self.repo)
        self.uncommitted = []
        self.unstaged = []
        self.both_changed = []

        try:
            expanded = itertools.chain.from_iterable(
                self.expand_path(Path(p)) for p in self.args
            )
            self.args = [p for p in expanded]
        except ValueError as e:
            self.repo.index.release_lock()
            self.stderr.write(f"fatal: {e}\n")
            self.exit(128)

        try:
            for path in self.args:
                self.plan_removal(path)
        except ValueError as e:
            self.repo.index.release_lock()
            self.stderr.write(f"fatal: {e}\n")
            self.exit(128)

        self.exit_on_errors()

        for path in self.args:
            self.remove_file(path)

        self.repo.index.write_updates()

        self.exit(0)

    def define_options(self) -> None:
        self.cached = "--cached" in self.args
        self.force = "-f" in self.args or "--force" in self.args
        self.recursive = "-r" in self.args

        self.args = [
            arg for arg in self.args if arg not in ("--cached", "-f", "--force", "-r")
        ]

    def expand_path(self, path):
        if self.repo.index.is_tracked_directory(path):
            if self.recursive:
                return self.repo.index.child_paths(path)
            else:
                raise ValueError(f"not removing '{path}' recursively without -r")

        if self.repo.index.is_tracked_file(path):
            return [path]

        raise ValueError(f"pathspec '{path}' did not match any files")

    def remove_file(self, path: str) -> None:
        self.repo.index.remove(Path(path))
        if not self.cached:
            self.repo.workspace.remove(Path(path))
        self.println(f"rm '{path}'")

    def plan_removal(self, path: str) -> None:
        if self.force:
            return

        stat_result = self.repo.workspace.stat_file(Path(path))
        if stat_result is not None and stat.S_ISDIR(stat_result.st_mode):
            raise ValueError(f"legit rm: '{path}': Operation not permitted")

        item = self.repo.database.load_tree_entry(self.head_oid, Path(path))
        entry = self.repo.index.entry_for_path(Path(path))

        staged_change = self.inspector.compare_tree_to_index(item, entry)
        if stat_result is not None:
            unstaged_change = self.inspector.compare_index_to_workspace(
                entry, stat_result
            )
        else:
            unstaged_change = None

        if staged_change is not None and unstaged_change is not None:
            self.both_changed.append(Path(path))
        elif staged_change is not None:
            if not self.cached:
                self.uncommitted.append(Path(path))
        elif unstaged_change is not None:
            if not self.cached:
                self.unstaged.append(Path(path))

    def exit_on_errors(self) -> None:
        if all(not x for x in (self.unstaged, self.uncommitted, self.both_changed)):
            return

        self.print_errors(self.both_changed, BOTH_CHANGED)
        self.print_errors(self.uncommitted, INDEX_CHANGED)
        self.print_errors(self.unstaged, WORKSPACE_CHANGED)

        self.repo.index.release_lock()

        self.exit(1)

    def print_errors(self, paths, message: str) -> None:
        if not paths:
            return

        files_have = "file has" if len(paths) == 1 else "files have"

        self.stderr.write(f"error: the following {files_have} {message}:\n")

        for path in paths:
            self.stderr.write(f"    {path}\n")
