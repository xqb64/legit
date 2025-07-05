from pathlib import Path


def assert_status(cmd, expected):
    assert cmd.status == expected, f"Expected status {expected}, got {cmd.status}"


def assert_stdout(stdout, expected):
    stdout.seek(0)
    data = stdout.read()
    assert data == expected, f"Expected stdout {expected!r}, got {data!r}"


def assert_stderr(stderr, expected):
    stderr.seek(0)
    data = stderr.read()
    assert data == expected, f"Expected stderr {expected!r}, got {data!r}"


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

