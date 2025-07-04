import os
import stat
import shutil
from typing import MutableMapping, TYPE_CHECKING, Optional
from collections.abc import Iterator
from pathlib import Path


if TYPE_CHECKING:
    from legit.migration import Migration


class Workspace:
    class MissingFile(Exception):
        pass
    class NoPermission(Exception):
        pass

    IGNORE: list[str] = [".", "..", ".git", "__pycache__", "env", ".pytest_cache", ".mypy_cache"]

    def __init__(self, path: Path) -> None:
        self.path: Path = path
    
    def write_file(self, path: Path, data: str, mode: Optional[int] = None, mkdir: bool = False) -> None:
        full_path: Path = self.path / path
        if mkdir:
            full_path.parent.mkdir(exist_ok=True, parents=True)

        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        with os.fdopen(os.open(full_path, flags), "w") as f:
            f.write(data)

        if mode:
            full_path.chmod(mode)

    def apply_migration(self, migration: 'Migration') -> None:
        self.apply_change_list(migration, "delete")

        for d in sorted(migration.rmdirs, key=lambda p: p.parts, reverse=True):
            self.remove_directory(d)

        for d in sorted(migration.mkdirs, key=lambda p: (len(p.parts), p)):
            self.make_directory(d)

        self.apply_change_list(migration, "update")
        self.apply_change_list(migration, "create")
   
    def remove(self, path: str):
        try:
            self._rm_rf(self.path / path)
            for parent in Path(path).parents:
                self.remove_directory(parent)
        except FileNotFoundError:
            pass

    def _rm_rf(self, path: Path) -> None:
       try:
           if path.is_dir():
               shutil.rmtree(path)
           else:
               path.unlink()
       except (FileNotFoundError, NotADirectoryError):
           pass

    def apply_change_list(self, migration: 'Migration', action: str) -> None:
        for filename, entry in migration.changes[action]:
            path = self.path / filename

            self._rm_rf(path)

            if action == "delete":
                continue
            
            p = path.parent

            while p != self.path and p.exists() and p.is_file():
                p.unlink()
                p = p.parent
            
            path.parent.mkdir(parents=True, exist_ok=True)

            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL

            assert entry is not None

            if entry.is_tree():
                self.make_directory(filename)
            else:
                data = migration.blob_data(entry.oid)
                with os.fdopen(os.open(path, flags, 0o644), "wb+") as f:
                    f.write(data.encode('utf-8'))
                path.chmod(entry.mode)


    def remove_directory(self, dirname: Path) -> None:
        try:
            os.rmdir(self.path / dirname)
        except OSError:
            pass

    def make_directory(self, dirname: Path) -> None:
        path = self.path / dirname
        stat_result = self.stat_file(dirname)

        if self._is_file(stat_result):
            path.unlink()

        path.mkdir(exist_ok=True, parents=True)

    def _is_file(self, stat_result: os.stat_result | None) -> bool:
        if stat_result is None:
            return False
        return stat.S_ISREG(stat_result.st_mode)

    def list_files(self, path: Path) -> Iterator[Path]:
        if path.is_dir():
            for f in path.iterdir():
                if f.name not in Workspace.IGNORE:
                    yield from self.list_files(f)
        elif path.exists():
            yield path.relative_to(self.path)
        else:
            raise Workspace.MissingFile(f"pathspec \"{path.relative_to(self.path)}\" did not match any files")

    def list_dir(self, dirname: str) -> MutableMapping[Path, os.stat_result]:
        stats = {}

        path = self.path / dirname
        
        entries = []
        for f in path.iterdir():
            if f.name not in Workspace.IGNORE:
                entries.append(f)

        for entry in entries:
            relative = (path / entry).relative_to(self.path)
            stats[relative] = (path / entry).stat()

        return stats

    def read_file(self, path: Path) -> str:
        try:
            with open(self.path / path) as f:
                return f.read()
        except PermissionError:
            raise Workspace.NoPermission(f"open(\"{path.name}\"): Permission denied")

    def stat_file(self, path: Path) -> Optional[os.stat_result]:
        try:
            return (self.path / path).stat()
        except FileNotFoundError:
            return None
        except PermissionError:
            raise Workspace.NoPermission(f"stat(\"{path.name}\"): Permission denied")

