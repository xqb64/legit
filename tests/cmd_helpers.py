from __future__ import annotations

import tempfile
from io import BufferedIOBase
from pathlib import Path

from contextlib import contextmanager
from typing import BinaryIO, Generator, cast
from typing_extensions import Buffer

from legit.cmd_base import Base


@contextmanager
def captured_stderr() -> Generator[CapturedStderr]:
    cs = CapturedStderr()
    try:
        yield cs
    finally:
        cs.close()


class CapturedStderr(BufferedIOBase):
    def __init__(self) -> None:
        self._file: BinaryIO = tempfile.TemporaryFile(mode="w+b")

    def fileno(self) -> int:
        return self._file.fileno()

    def write(self, s: Buffer) -> int:
        if isinstance(s, str):
            s = s.encode()
        n = self._file.write(s)
        self._file.flush()
        return n

    def flush(self) -> None:
        return self._file.flush()

    def read(self, n: int | None = -1) -> bytes:
        self._file.flush()
        self._file.seek(0)
        if n is not None:
            return self._file.read(n)
        return self._file.read()

    def readline(self, n: int | None = -1) -> bytes:
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


def assert_stdout(stdout: BinaryIO, expected: str) -> None:
    stdout.seek(0)
    data = stdout.read()
    assert data == expected.encode(), f"Expected stdout {expected!r}, got {data!r}"


def assert_stderr(stderr: BinaryIO, expected: str) -> None:
    stderr.seek(0)
    data = stderr.read()
    assert data == expected.encode(), f"Expected stderr {expected!r}, got {data!r}"


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


def assert_index(repo, expected: dict[str, str]) -> None:
    files = {}
    repo.index.load()

    for entry in repo.index.entries.values():
        files[str(entry.path)] = repo.database.load(entry.oid).data.decode("utf-8")

    assert files == expected
