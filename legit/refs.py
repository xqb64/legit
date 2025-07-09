import re
from pathlib import Path
from sys import path_hooks
from typing import Any, Optional, Callable
from legit.lockfile import Lockfile
from collections import defaultdict

INVALID_NAME = re.compile(
    r"""
      ^\.
    | /\.
    | \.\.
    | /$
    | \.lock$
    | @\{
    | [\x00-\x20*:?\[\\\^~\x7f]
""",
    re.VERBOSE,
)


class Refs:
    class LockDenied(Exception):
        pass

    class InvalidBranch(Exception):
        pass

    class Ref:
        def __init__(self, oid: str) -> None:
            self.oid: str = oid

        def read_oid(self) -> str:
            return self.oid

        def __eq__(self, other: object) -> bool:
            if not isinstance(other, Refs.Ref):
                return NotImplemented
            return self.oid == other.oid

        def __hash__(self) -> int:
            return hash(self.oid)

    class SymRef:
        def __init__(self, refs: "Refs", path: str) -> None:
            self.path: str = path
            self.refs: Refs = refs

        def is_branch(self) -> bool:
            return self.path.startswith("refs/heads/")

        def is_remote(self) -> bool:
            return self.path.startswith("refs/remotes/")

        def read_oid(self) -> Optional[str]:
            return self.refs.read_ref(self.path)

        def is_head(self) -> bool:
            return self.path == Refs.HEAD

        def short_name(self) -> str:
            return self.refs.short_name(self.path)

        def __eq__(self, other: object) -> bool:
            if not isinstance(other, Refs.SymRef):
                return NotImplemented
            return self.refs is other.refs and self.path == other.path

        def __hash__(self) -> int:
            return hash((id(self.refs), self.path))

    HEAD = "HEAD"
    SYMREF = re.compile(r"^ref: (.+)$")

    REFS_DIR = Path("refs")
    HEADS_DIR = REFS_DIR / "heads"
    REMOTES_DIR = REFS_DIR / "remotes"

    def __init__(self, path: Path) -> None:
        self.path: Path = path
        self.refs_path: Path = self.path / self.REFS_DIR
        self.heads_path: Path = self.path / self.HEADS_DIR
        self.remotes_path: Path = self.path / self.REMOTES_DIR

    def reverse_refs(self) -> dict[str, list["Refs.Ref | Refs.SymRef"]]:
        table: dict[str, list["Refs.Ref | Refs.SymRef"]] = defaultdict(list)

        for ref in self.list_all_refs():
            oid = ref.read_oid()
            if oid is not None:
                table[oid].append(ref)

        return table

    def long_name(self, ref: str) -> str:
        path = self.path_for_name(ref)
        if path is not None:
            return str(path.relative_to(self.path))
        raise self.InvalidBranch(
            f"the requested upstream branch '{ref}' does not exist"
        )

    def list_remotes(self):
        return self.list_refs(self.remotes_path)

    def list_all_refs(self):
        return [Refs.SymRef(self, Refs.HEAD)] + self.list_refs(self.refs_path)

    def short_name(self, path: str) -> str:
        full_path = self.path / path

        prefix = None

        for base_dir in [self.remotes_path, self.heads_path, self.path]:
            if full_path.is_relative_to(base_dir):
                prefix = base_dir
                break

        if prefix is None:
            raise ValueError("Path is not within any known prefix directory.")

        return str(full_path.relative_to(prefix))

    def list_branches(self) -> list["Refs.SymRef"]:
        return self.list_refs(self.heads_path)

    def list_refs(self, dirname: Path) -> list["Refs.SymRef"]:
        try:
            entries = list(dirname.iterdir())
        except FileNotFoundError:
            return []

        refs: list["Refs.SymRef"] = []
        for path in entries:
            if path.is_dir():
                refs.extend(self.list_refs(path))
            else:
                rel_path = path.relative_to(self.path)
                refs.append(Refs.SymRef(self, str(rel_path)))
        return refs

    def current_ref(self, source: str = "HEAD") -> "Refs.SymRef":
        ref = self.read_oid_or_symref(self.path / source)

        if isinstance(ref, Refs.SymRef):
            return self.current_ref(ref.path)

        return Refs.SymRef(self, source)

    def set_head(self, revision: str, oid: str) -> None:
        head = self.path / Refs.HEAD
        path = self.heads_path / revision

        if path.is_file():
            relative = path.relative_to(self.path)
            self._update_ref_file(head, f"ref: {relative}")
        else:
            self._update_ref_file(head, oid)

    def read_oid_or_symref(self, path: Path) -> Optional["Refs.Ref | Refs.SymRef"]:
        try:
            data = path.read_text().strip()
        except FileNotFoundError:
            return None
        m = Refs.SYMREF.match(data)
        return Refs.SymRef(self, m.group(1)) if m else Refs.Ref(data)

    def read_symref(self, path: Path) -> Optional[str]:
        ref = self.read_oid_or_symref(Path(path))
        match ref:
            case c if isinstance(c, Refs.Ref):
                assert isinstance(ref, Refs.Ref)
                return ref.oid
            case c if isinstance(c, Refs.SymRef):
                assert isinstance(ref, Refs.SymRef)
                return self.read_symref(self.path / ref.path)

    def read_head(self) -> Optional[str]:
        head = self.read_symref(self.path / Refs.HEAD)
        return head

    def update_head(self, oid: str) -> Optional[str]:
        return self.update_symref(self.path / Refs.HEAD, oid)

    def update_ref(self, name: str, oid: str) -> None:
        self._update_ref_file(self.path / name, oid)

    def update_symref(self, path: Path, oid: str) -> Optional[str]:
        lockfile = Lockfile(path)
        lockfile.hold_for_update()

        ref = self.read_oid_or_symref(path)
        if not isinstance(ref, Refs.SymRef):
            self.write_lockfile(lockfile, oid)
            return ref.oid if ref is not None else None

        try:
            return self.update_symref(self.path / ref.path, oid)
        finally:
            lockfile.rollback()

    def write_lockfile(self, lockfile: Lockfile, oid: Optional[str]) -> None:
        assert oid is not None
        lockfile.write(oid.encode("utf-8") + b"\n")
        lockfile.commit()

    def create_branch(self, branch_name: str, start_oid: str) -> str:
        if INVALID_NAME.search(branch_name):
            raise Refs.InvalidBranch(f"'{branch_name}' is not a valid branch name.")

        path = self.heads_path / branch_name
        if path.is_file():
            raise Refs.InvalidBranch(f"A branch named '{branch_name}' already exists.")

        return self._update_ref_file(path, start_oid)

    class StaleValue(Exception):
        pass

    def compare_and_swap(
        self,
        name: str,
        old_oid: Optional[str],
        new_oid: Optional[str],
    ) -> None:
        path = self.path / name

        def guard() -> None:
            if old_oid != self.read_symref(path):
                raise self.StaleValue(f"value of {name} changed since last read")

        self._update_ref_file(path, new_oid, guard)

    def _update_ref_file(
        self,
        path: Path,
        oid: Optional[str],
        callback: Optional[Callable[[], Any]] = None,
    ) -> None:
        lockfile = Lockfile(path)

        try:
            lockfile.hold_for_update()

            if callback:
                callback()

            if oid is not None:
                self.write_lockfile(lockfile, oid)
            else:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                lockfile.rollback()

        except Lockfile.MissingParent:
            path.parent.mkdir(parents=True, exist_ok=True)
            return self._update_ref_file(path, oid, callback)

        except Exception:
            lockfile.rollback()
            raise

    def read_ref(self, name: str) -> Optional[str]:
        path = self.path_for_name(name)
        return self.read_symref(path) if path is not None else None

    def path_for_name(self, name: str) -> Optional[Path]:
        prefixes = (self.path, self.refs_path, self.heads_path, self.remotes_path)
        for prefix in prefixes:
            candidate = prefix / name
            if candidate.is_file():
                return candidate
        return None

    def read_ref_file(self, path: Path) -> Optional[str]:
        try:
            return path.read_text().strip()
        except FileNotFoundError:
            return None

    def delete_branch(self, branch_name: str) -> str:
        path = self.heads_path / branch_name
        lock = Lockfile(path)

        try:
            lock.hold_for_update()

            oid = self.read_symref(path)
            if not oid:
                raise Refs.InvalidBranch(f"branch '{branch_name}' not found.")

            path.unlink()
            self._delete_parent_directories(path)

            return oid

        finally:
            lock.rollback()

    def _delete_parent_directories(self, path: Path) -> None:
        p = path.parent
        while p != self.heads_path and p.exists() and not any(p.iterdir()):
            p.rmdir()
            p = p.parent
