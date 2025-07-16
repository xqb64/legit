import shutil
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import (
    Callable,
    Generator,
    Mapping,
    Optional,
    Protocol,
    TextIO,
    TypeAlias,
    cast,
)

import pytest
from freezegun import freeze_time

from legit.blob import Blob
from legit.cmd_base import Base
from legit.command import Command
from legit.commit import Commit as CommitObj
from legit.editor import Editor
from legit.pack import Record
from legit.repository import Repository
from legit.revision import Revision
from legit.tree import Tree
from tests.cmd_helpers import CapturedStderr

LegitCmdResult: TypeAlias = tuple[Base, StringIO, StringIO, CapturedStderr]

ResolveRevision: TypeAlias = Callable[[str], str]
LoadCommit: TypeAlias = Callable[[str], Blob | CommitObj | Tree | Record]
WriteFile: TypeAlias = Callable[[str, str], None]
Mkdir: TypeAlias = Callable[[str], None]
Touch: TypeAlias = Callable[[str], None]
Delete: TypeAlias = Callable[[str], None]
MakeExecutable: TypeAlias = Callable[[str], None]
MakeUnreadable: TypeAlias = Callable[[str], None]
EditBlock: TypeAlias = Callable[[Editor], None]
StubEditorFactory: TypeAlias = Callable[[str], None]


class LegitCmd(Protocol):
    def __call__(
        self,
        *argv: str,
        env: Mapping[str, str] | None = None,
        stdin_data: str = "",
    ) -> "LegitCmdResult": ...


class Commit(Protocol):
    def __call__(
        self, message: str, when: Optional[datetime] = ..., author: bool = ...
    ) -> LegitCmdResult: ...


@pytest.fixture
def load_commit(repo: Repository, resolve_revision: ResolveRevision) -> LoadCommit:
    def _load_commit(expression: str) -> Blob | CommitObj | Tree | Record:
        return repo.database.load(resolve_revision(expression))

    return _load_commit


@pytest.fixture
def resolve_revision(repo: Repository) -> ResolveRevision:
    def _resolve_revision(expression: str) -> str:
        return Revision(repo, expression).resolve()

    return _resolve_revision


@pytest.fixture
def repo_path(tmp_path: Path) -> Path:
    return tmp_path / "test_repo"


@pytest.fixture(autouse=True)
def setup_and_teardown(repo_path: Path) -> Generator[None]:
    Command.execute(
        repo_path, {}, ["legit", "init"], StringIO(), StringIO(), StringIO()
    )
    yield
    shutil.rmtree(repo_path, ignore_errors=True)


@pytest.fixture
def repo(repo_path: Path) -> Generator[Repository]:
    git_dir = repo_path / ".git"
    repo_instance = Repository(git_dir)
    try:
        yield repo_instance
    finally:
        repo_instance.close()


@pytest.fixture
def commit(legit_cmd: LegitCmd) -> Commit:
    def _commit(
        message: str, when: Optional[datetime] = None, author: bool = True
    ) -> LegitCmdResult:
        if author:
            env = {
                "GIT_AUTHOR_NAME": "A. U. Thor",
                "GIT_AUTHOR_EMAIL": "author@example.com",
            }
        else:
            env = {}

        if when is None:
            when = datetime.now().astimezone()

        with freeze_time(when):
            return legit_cmd("commit", "-m", message, env=env)

    return _commit


@pytest.fixture
def write_file(repo_path: Path) -> WriteFile:
    def _write_file(name: str, contents: str) -> None:
        path = repo_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(contents)

    return _write_file


@pytest.fixture
def mkdir(repo_path: Path) -> Mkdir:
    def _mkdir(name: str) -> None:
        path = repo_path / name
        path.mkdir(parents=True, exist_ok=True)

    return _mkdir


@pytest.fixture
def touch(repo_path: Path) -> Touch:
    def _touch(name: str) -> None:
        path = repo_path / name
        path.touch()

    return _touch


@pytest.fixture
def delete(repo_path: Path) -> Delete:
    def _delete(name: str) -> None:
        path = repo_path / name
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)

    return _delete


@pytest.fixture
def make_executable(repo_path: Path) -> MakeExecutable:
    def _make_executable(name: str) -> None:
        path = repo_path / name
        path.chmod(0o755)

    return _make_executable


@pytest.fixture
def make_unreadable(repo_path: Path) -> MakeUnreadable:
    def _make_unreadable(name: str) -> None:
        path = repo_path / name
        path.chmod(0o200)

    return _make_unreadable


@pytest.fixture
def legit_cmd(repo_path: Path) -> Generator[LegitCmd]:
    to_close = []

    def _legit_cmd(
        *argv: str,
        env: Mapping[str, str] | None = None,
        stdin_data: str = "",
    ) -> LegitCmdResult:
        env = env or {}
        stdin = StringIO(stdin_data)
        stdout = StringIO()
        stderr = CapturedStderr()
        to_close.append(stderr)
        cmd = Command.execute(
            repo_path,
            cast(dict[str, str], env),
            ["legit"] + list(argv),
            stdin,
            stdout,
            cast(TextIO, stderr),
        )
        return cmd, stdin, stdout, stderr

    yield _legit_cmd

    for s in to_close:
        s.close()


@pytest.fixture
def stub_editor(monkeypatch: pytest.MonkeyPatch) -> StubEditorFactory:
    def factory(message_to_return: str) -> None:
        def fake_edit(
            path: Path, command: str | None = None, *, block: EditBlock | None = None
        ) -> str:
            if block is not None:
                block(Editor(path, command))
            return message_to_return

        monkeypatch.setattr(Editor, "edit", fake_edit)

    return factory
