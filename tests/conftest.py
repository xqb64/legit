from datetime import datetime 
import shutil
from typing import Optional
import pytest
from pathlib import Path
from io import StringIO
from freezegun import freeze_time

from legit.repository import Repository
from legit.command import Command
from legit.revision import Revision


@pytest.fixture
def load_commit(repo, resolve_revision):
    def _load_commit(expression):
        return repo.database.load(resolve_revision(expression))
    return _load_commit


@pytest.fixture
def resolve_revision(repo):
    """
    Returns a function that can resolve a revision expression to its object ID.
    """
    def _resolve_revision(expression):
        return Revision(repo, expression).resolve()
    
    return _resolve_revision


@pytest.fixture
def repo_path(tmp_path):
    """
    Create a fresh test repository path under pytest's tmp_path.
    """
    return tmp_path / "test_repo"

@pytest.fixture(autouse=True)
def setup_and_teardown(repo_path):
    """
    Initialize a repository before each test and clean up afterward.
    """
    # initialize repository (e.g., `init` command)
    Command.execute(repo_path, {}, ["legit", "init"], StringIO(), StringIO(), StringIO())
    yield
    # teardown: remove the repo directory
    shutil.rmtree(repo_path, ignore_errors=True)

@pytest.fixture
def repo(repo_path):
    """
    Provide a Repository instance pointed at the .git directory.
    """
    git_dir = repo_path / ".git"
    return Repository(git_dir)

@pytest.fixture
def commit(legit_cmd):
    def _commit(message: str, when: Optional[datetime] = None, author: bool = True):
        if author:
            env = {
                "GIT_AUTHOR_NAME": "A. U. Thor",
                "GIT_AUTHOR_EMAIL": "author@example.com",
            }
        else:
            env = {}
    
        if when is None:
            when = datetime.now()
    
        with freeze_time(when):
            return legit_cmd("commit", "-m", message, env=env)

    return _commit


@pytest.fixture
def write_file(repo_path):
    """
    Write `contents` to `repo_path/name`, creating parent dirs as needed.
    """
    def _write_file(name: str, contents: str):
        path = repo_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            f.write(contents)
    return _write_file


@pytest.fixture
def mkdir(repo_path):
    """
    Make a directory in `repo_path`.
    """
    def _mkdir(name: str):
        path = repo_path / name
        path.mkdir(parents=True, exist_ok=True)
    return _mkdir

@pytest.fixture
def touch(repo_path):
    """
    Touch a file in `repo_path`.
    """
    def _touch(name: str):
        path = repo_path / name
        path.touch()
    return _touch

@pytest.fixture
def delete(repo_path):
    """
    Delete a file in `repo_path`.
    """
    def _delete(name: str):
        path = repo_path / name
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
    return _delete

@pytest.fixture
def make_executable(repo_path):
    """
    Make the file at `repo_path/name` executable (0755).
    """
    def _make_executable(name: str):
        path = repo_path / name
        path.chmod(0o755)
    return _make_executable

@pytest.fixture
def make_unreadable(repo_path):
    """
    Make the file at `repo_path/name` unreadable (0200).
    """
    def _make_unreadable(name: str):
        path = repo_path / name
        path.chmod(0o200)
    return _make_unreadable

@pytest.fixture
def legit_cmd(repo_path):
    """
    Run the command with StringIO streams and return (cmd, stdin, stdout, stderr).
    """
    def _legit_cmd(*argv, env={}, stdin_data=""):
        stdin = StringIO(stdin_data)
        stdout = StringIO()
        stderr = StringIO()
        cmd = Command.execute(repo_path, env, ["legit"] + list(argv), stdin, stdout, stderr)
        return cmd, stdin, stdout, stderr
    return _legit_cmd


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


def assert_noent(repo_path, filename: str):
    target_path = repo_path / filename
    assert not target_path.exists(), f"Expected path '{target_path}' to not exist, but it does."


@pytest.fixture
def committed_repo(write_file, legit_cmd, commit):
    write_file("1.txt", "one")
    write_file("a/2.txt", "two")
    write_file("a/b/3.txt", "three")
    legit_cmd("add", ".")
    commit("commit message")
