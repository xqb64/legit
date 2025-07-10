from io import StringIO
from pathlib import Path
from typing import Any, TextIO, cast

from legit.cmd_base import Base
from legit.command import Command
from legit.repository import Repository
from tests.cmd_helpers import CapturedStderr


class RemoteRepo:
    def __init__(self, name: str) -> None:
        self.name = name
        self.repo_path: Path | None = None

    @property
    def repo(self) -> Repository:
        assert self.repo_path is not None
        return Repository(self.repo_path / ".git")

    def path(self, repo_path: Path | None) -> Path:
        if self.repo_path is None:
            self.repo_path = Path(f"{repo_path}-{self.name}")
        return self.repo_path

    def write_file(self, *args: Any) -> None:
        if len(args) == 2:
            repo_path = None
            name, contents = args
        elif len(args) == 3:
            repo_path, name, contents = args
        else:
            raise TypeError(
                "write_file expects (name, contents) or (repo_path, name, contents)"
            )

        root = self.path(repo_path)
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)

    def legit_cmd(
        self,
        repo_path: Path,
        *argv: Any,
        env: dict[str, str] | None = None,
        stdin_data: str = "",
    ) -> tuple[Base, StringIO, StringIO, CapturedStderr]:
        env = env or {}
        stdin = StringIO(stdin_data)
        stdout = StringIO()
        stderr = CapturedStderr()
        cmd = Command.execute(
            self.path(repo_path),
            env,
            ["legit"] + list(argv),
            stdin,
            stdout,
            cast(TextIO, stderr),
        )
        return cmd, stdin, stdout, stderr
