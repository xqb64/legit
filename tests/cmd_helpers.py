from __future__ import annotations

import tempfile
from contextlib import contextmanager
from io import TextIOBase
from pathlib import Path
from typing import Generator, TextIO, cast

from legit.blob import Blob
from legit.cmd_base import Base
from legit.repository import Repository


@contextmanager
def captured_stderr() -> Generator[CapturedStderr]:
    cs = CapturedStderr()
    try:
        yield cs
    finally:
        cs.close()


class CapturedStderr(TextIOBase):
    def __init__(self) -> None:
        self._file: TextIO = tempfile.TemporaryFile(mode="w+")

    def fileno(self) -> int:
        return self._file.fileno()

    def write(self, s: str) -> int:
        n = self._file.write(s)
        self._file.flush()
        return n

    def flush(self) -> None:
        return self._file.flush()

    def read(self, n: int | None = -1) -> str:
        self._file.flush()
        self._file.seek(0)
        if n is not None:
            return self._file.read(n)
        return self._file.read()

    def readline(self, n: int | None = -1) -> str:  # type: ignore[override]
        self._file.seek(0)
        if n is not None:
            return self._file.readline(n)
        return self._file.readline()

    def close(self) -> None:
        return self._file.close()

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._file.seek(offset, whence)


def assert_status(cmd: Base, expected: int) -> None:
    assert cmd.status == expected, f"Expected status {expected}, got {cmd.status}"


def assert_stdout(stdout: TextIO, expected: str) -> None:
    stdout.seek(0)
    data = stdout.read()
    assert data == expected, f"Expected stdout {expected!r}, got {data!r}"


def assert_stderr(stderr: CapturedStderr | TextIO, expected: str) -> None:
    stderr.seek(0)
    data = stderr.read()
    assert data == expected, f"Expected stderr {expected!r}, got {data!r}"


def _snapshot_workspace(repo_path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in repo_path.rglob("*"):
        if ".git" in path.parts or not path.is_file():
            continue
        result[str(path.relative_to(repo_path))] = path.read_text()
    return result


def assert_workspace(repo_path: Path, expected: dict[str, str]) -> None:
    actual = _snapshot_workspace(repo_path)
    assert actual == expected, f"workspace mismatch – expected {expected}, got {actual}"


def assert_noent(repo_path: Path, name: str) -> None:
    assert not (repo_path / name).exists(), f"{name} should not exist in the workspace"


def assert_index(repo: Repository, expected: dict[str, str]) -> None:
    files = {}
    repo.index.load()

    for entry in repo.index.entries.values():
        files[str(entry.path)] = cast(Blob, repo.database.load(entry.oid)).data.decode(
            "utf-8"
        )

    assert files == expected
