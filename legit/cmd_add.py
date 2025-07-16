from __future__ import annotations

from pathlib import Path

from legit.blob import Blob
from legit.cmd_base import Base
from legit.lockfile import Lockfile
from legit.workspace import Workspace


class Add(Base):
    def run(self) -> None:
        try:
            self.repo.index.load_for_update()

            for path in self.expanded_paths():
                self.add_to_index(path)

            self.repo.index.write_updates()
        except Lockfile.LockDenied as e:
            self.handle_locked_index(e)
        except Workspace.MissingFile as e:
            self.handle_missing_file(e)
        except Workspace.NoPermission as e:
            self.handle_no_permission(e)

    def handle_locked_index(self, exc: Exception) -> None:
        self.stderr.write(f"fatal: {exc}\n\n")
        self.stderr.write(
            "Another legit process seems to be running in this repository.\n"
            "Please make sure all processes are terminated then try again.\n"
            "If it still fails, a legit process may have crashed in this\n"
            "repository earlier: remove the file manually to continue.\n"
        )
        self.exit(128)

    def handle_missing_file(self, exc: Exception) -> None:
        self.stderr.write(f"fatal: {exc}\n")
        self.repo.index.release_lock()
        self.exit(128)

    def handle_no_permission(self, exc: Exception) -> None:
        self.stderr.write(f"error: {exc}\n")
        self.stderr.write("fatal: adding files failed\n")
        self.repo.index.release_lock()
        self.exit(128)

    def expanded_paths(self) -> list[Path]:
        paths = []
        for path in self.args:
            abs_path = self.expanded_path(path)
            for f in self.repo.workspace.list_files(abs_path):
                paths.append(f)
        return paths

    def add_to_index(self, path: Path) -> None:
        data = self.repo.workspace.read_file(path)
        stat = self.repo.workspace.stat_file(path)
        assert stat is not None

        blob = Blob(data)
        self.repo.database.store(blob)
        self.repo.index.add(path, blob.oid, stat)
