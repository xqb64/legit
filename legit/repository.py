import re
import os
from pathlib import Path
from typing import Optional

from legit.blob import Blob
from legit.commit import Commit
from legit.tree import DatabaseEntry
from legit.database import Database
from legit.index import Index
from legit.refs import Refs
from legit.workspace import Workspace
from legit.status import Status
from legit.migration import Migration
from legit.lockfile import Lockfile
from legit.config_stack import ConfigStack
from legit.config import ConfigFile
from legit.remotes import Remotes
from legit.common_ancestors import CommonAncestors


UNSAFE_MESSAGE = "You seem to have moved HEAD. Not rewinding, check your HEAD!"


class Repository:
    def __init__(self, git_path: Path):
        self.git_path: Path = git_path
        self.database: Database = Database(git_path / "objects")
        self.index: Index = Index(git_path / "index")
        self.refs: Refs = Refs(git_path)
        self.workspace: Workspace = Workspace(git_path.parent)
        self.config: ConfigStack = ConfigStack(self.git_path)
        self.remotes: Remotes = Remotes(self.config.file("local"))
    
    def divergence(self, ref):
        return Divergence(self, ref)

    def status(self, commit_oid: Optional[str] = None) -> Status:
        return Status(self, commit_oid)

    def migration(self, tree_diff: dict[Path, list[DatabaseEntry]]) -> "Migration":
        return Migration(self, tree_diff)

    def pending_commit(self) -> "PendingCommit":
        return PendingCommit(self.git_path)

    def hard_reset(self, oid: str) -> None:
        HardReset(self, oid).execute()


class HardReset:
    def __init__(self, repo: Repository, oid: str) -> None:
        self.repo = repo
        self.oid = oid

    def execute(self) -> None:
        self.status = self.repo.status(self.oid)
        changed = [Path(path) for path in self.status.changed]

        for path in changed:
            self.reset_path(path)

    def reset_path(self, path: Path) -> None:
        self.repo.index.remove(path)
        self.repo.workspace.remove(path)

        entry = self.status.head_tree.get(path)
        if entry is None:
            return

        blob = self.repo.database.load(entry.oid)
        self.repo.workspace.write_file(path, blob.data, entry.mode, True)

        stat = self.repo.workspace.stat_file(path)
        self.repo.index.add(path, entry.oid, stat)


class PendingCommit:
    class Error(Exception):
        pass

    HEAD_FILES = {
        "merge": "MERGE_HEAD",
        "cherry_pick": "CHERRY_PICK_HEAD",
        "revert": "REVERT_HEAD",
    }

    def __init__(self, path: Path) -> None:
        self.path = path
        self.message_path = path / "MERGE_MSG"

    def merge_oid(self, ty: str = "merge"):
        head_path = self.path / PendingCommit.HEAD_FILES[ty]
        try:
            return head_path.read_text().strip()
        except FileNotFoundError:
            name = head_path.name
            raise PendingCommit.Error(
                f"There is no merge in progress ({name} missing)."
            )

    @property
    def merge_message(self):
        return self.message_path.read_text()

    def start(self, oid: str, ty: str = "merge") -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        with os.fdopen(
            os.open(self.path / PendingCommit.HEAD_FILES[ty], flags, 0o644), "w"
        ) as f:
            f.write(oid)

    def clear(self, ty: str = "merge") -> None:
        head_path = self.path / PendingCommit.HEAD_FILES[ty]
        try:
            head_path.unlink()
            self.message_path.unlink()
        except FileNotFoundError:
            name = head_path.name
            raise PendingCommit.Error(f"There is no merge to abort ({name} missing).")

    def is_in_progress(self) -> bool:
        return self.merge_type() is not None

    def merge_type(self) -> Optional[str]:
        for ty, name in PendingCommit.HEAD_FILES.items():
            path = self.path / name
            if path.exists():
                return ty
        return None


class Sequencer:
    def __init__(self, repo: Repository) -> None:
        self.repo: Repository = repo
        self.path = self.repo.git_path / "sequencer"
        self.todo_path = self.path / "todo"
        self.todo_file = None
        self.abort_path = self.path / "aborty-safety"
        self.head_path = self.path / "head"
        self.commands = []
        self.config: ConfigFile = ConfigFile(self.path / "opts")

    def start(self, options) -> None:
        self.path.mkdir(parents=True, exist_ok=False)

        self.config.open_for_update()
        for k, v in options.items():
            if v is not None:
                self.config.set(["options", k], v)
        self.config.save()

        head_oid = self.repo.refs.read_head()
        self.write_file(self.head_path, head_oid)
        self.write_file(self.abort_path, head_oid)

        self.open_todo_file()

    def get_option(self, name: str) -> str:
        self.config.open()
        return self.config.get(["options", name])

    def write_file(self, path: Path, data: str) -> None:
        lockfile = Lockfile(path)
        lockfile.hold_for_update()
        lockfile.write(data.encode("utf-8") + b"\n")
        lockfile.commit()

    def pick(self, commit: Commit) -> None:
        self.commands.append(("pick", commit))

    def revert(self, commit: Commit) -> None:
        self.commands.append(("revert", commit))

    def next_command(self):
        try:
            return self.commands[0]
        except IndexError:
            return None

    def drop_command(self) -> None:
        self.commands.pop(0)
        self.write_file(self.abort_path, self.repo.refs.read_head())

    def open_todo_file(self) -> None:
        if not self.path.is_dir():
            return

        self.todo_file = Lockfile(self.todo_path)
        self.todo_file.hold_for_update()

    def dump(self) -> None:
        if self.todo_file is None:
            return

        for action, commit in self.commands:
            short = self.repo.database.short_oid(commit.oid)
            self.todo_file.write(
                f"{action} {short} {commit.title_line()}\n".encode("utf-8")
            )

        self.todo_file.commit()

    def load(self) -> None:
        self.open_todo_file()
        if not self.todo_path.exists():
            return

        for line in self.todo_path.read_text().splitlines():
            action, oid, _rest = re.compile(r"^(\S+) (\S+) (.*)$").match(line).groups()
            oids = self.repo.database.prefix_match(oid)
            commit = self.repo.database.load(oids[0])
            self.commands.append((action, commit))

    def quit(self) -> None:
        import shutil

        shutil.rmtree(self.path)

    def abort(self) -> None:
        head_oid = self.head_path.read_text().strip()
        expected = self.abort_path.read_text().strip()
        actual = self.repo.refs.read_head()

        self.quit()

        if actual != expected:
            raise ValueError(UNSAFE_MESSAGE)

        self.repo.hard_reset(head_oid)
        orig_head = self.repo.refs.update_head(head_oid)
        self.repo.refs.update_ref("ORIG_HEAD", orig_head)


class Divergence:
    def __init__(self, repo, ref) -> None:
        self.upstream = repo.remotes.get_upstream(ref.short_name())
        if self.upstream is None:
            return

        left = ref.read_oid()
        right = repo.refs.read_ref(self.upstream)
        common: CommonAncestors = CommonAncestors(repo.database, left, [right])

        common.find()

        self.ahead, self.behind = common.counts()
