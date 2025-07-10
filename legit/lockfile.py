from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO


class Lockfile:
    class MissingParent(Exception):
        pass

    class NoPermission(Exception):
        pass

    class StaleLock(Exception):
        pass

    class LockDenied(Exception):
        pass

    def __init__(self, path: Path) -> None:
        self.path: Path = path
        self.lock_path: Path = path.with_suffix(".lock")
        self.lock: BinaryIO | None = None

    def rollback(self) -> None:
        self.raise_on_stale_lock()

        assert self.lock is not None
        self.lock.close()

        self.lock_path.unlink()
        self.lock = None

    def hold_for_update(self) -> bool:
        if self.lock is None:
            flags: int = os.O_RDWR | os.O_CREAT | os.O_EXCL
            mode: int = 0o644
            try:
                self.lock = os.fdopen(os.open(self.lock_path, flags, mode), "wb+")
                return True
            except FileExistsError:
                raise Lockfile.LockDenied(
                    f"Unable to create '{self.lock_path}': File exists."
                )
            except PermissionError:
                raise Lockfile.NoPermission
            except FileNotFoundError:
                self.lock_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    self.lock = os.fdopen(os.open(self.lock_path, flags, mode), "wb+")
                    return True
                except FileExistsError:
                    raise Lockfile.LockDenied(
                        f"Unable to create '{self.lock_path}': File exists."
                    )
        return False

    def write(self, data: bytes) -> None:
        self.raise_on_stale_lock()

        assert self.lock is not None
        self.lock.write(data)

    def commit(self) -> None:
        self.raise_on_stale_lock()

        assert self.lock is not None
        self.lock.close()

        self.lock_path.rename(self.path)

        self.lock = None

    def raise_on_stale_lock(self) -> None:
        if self.lock is None:
            raise Lockfile.StaleLock
