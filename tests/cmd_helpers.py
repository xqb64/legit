import os
import tempfile
from io import TextIOBase, BufferedIOBase
from pathlib import Path

from contextlib import contextmanager

@contextmanager
def captured_stderr():
    cs = CapturedStderr()
    try:
        yield cs
    finally:
        cs.close()    

class CapturedStderr(TextIOBase):
    """
    A file-like that hands subprocess a real fileno() but lets us
    read() everything later as text.
    """
    def __init__(self):
        # open a real temp file in text mode
        self._file = tempfile.TemporaryFile(mode="w+")

    def fileno(self):
        return self._file.fileno()

    def write(self, s):
        n = self._file.write(s)
        self._file.flush()
        return n

    def flush(self):
        return self._file.flush()

    def read(self, *args):
        # rewind before reading
        self._file.flush()
        self._file.seek(0)
        return self._file.read(*args).encode()

    def readline(self, *args):
        # rewind before reading a line
        self._file.seek(0)
        return self._file.readline(*args).encode()

    def close(self):
        return self._file.close()

    def seek(self, *args):
        return self._file.seek(*args)


def assert_status(cmd, expected):
    assert cmd.status == expected, f"Expected status {expected}, got {cmd.status}"


def assert_stdout(stdout, expected):
    stdout.seek(0)
    data = stdout.read()
    assert data == expected.encode(), f"Expected stdout {expected!r}, got {data!r}"


def assert_stderr(stderr, expected):
    stderr.seek(0)
    data = stderr.read()
    assert data == expected.encode(), f"Expected stderr {expected!r}, got {data!r}"


def _snapshot_workspace(repo_path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in repo_path.rglob("*"):
        if ".git" in path.parts or not path.is_file():
            continue
        result[path.relative_to(repo_path).as_posix()] = path.read_text()
    return result


def assert_workspace(repo_path: Path, expected: dict[str, str]):
    actual = _snapshot_workspace(repo_path)
    assert actual == expected, f"workspace mismatch – expected {expected}, got {actual}"


def assert_noent(repo_path: Path, name: str):
    assert not (repo_path / name).exists(), f"{name} should not exist in the workspace"


def assert_index(repo, expected: dict[str, str]):
    files = {}
    repo.index.load()

    for entry in repo.index.entries.values():
        files[str(entry.path)] = repo.database.load(entry.oid).data.decode('utf-8')

    assert files == expected

