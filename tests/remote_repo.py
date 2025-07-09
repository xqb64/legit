from io import BytesIO
from pathlib import Path
from legit.command import Command
from legit.repository import Repository
from tests.cmd_helpers import CapturedStderr


class RemoteRepo:
    def __init__(self, name: str):
        self.name = name
        self.repo_path: Path | None = None

    @property
    def repo(self):
        return Repository(self.repo_path / ".git")

    def path(self, repo_path) -> Path:
        if self.repo_path is None:
            self.repo_path = Path(f"{repo_path}-{self.name}")
        return self.repo_path

    def write_file(self, *args):
        if len(args) == 2:  # called from inside a fixture
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

    def legit_cmd(self, repo_path, *argv, env={}, stdin_data=""):
        stdin = BytesIO(stdin_data.encode("utf-8"))
        stdout = BytesIO()
        stderr = CapturedStderr()
        cmd = Command.execute(
            self.path(repo_path), env, ["legit"] + list(argv), stdin, stdout, stderr
        )
        return cmd, stdin, stdout, stderr
