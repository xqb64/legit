from functools import cache
from pathlib import Path
from typing import MutableMapping, TextIO
from legit.cmd_color import Color
from legit.pager import Pager
from legit.editor import Editor
from legit.repository import Repository


class Base:
    def __init__(
        self,
        _dir: Path,
        env: MutableMapping[str, str],
        args: list[str],
        stdin: TextIO,
        stdout: TextIO,
        stderr: TextIO,
    ):
        self.dir: Path = _dir
        self.env: MutableMapping[str, str] = env
        self.args: list[str] = args
        self.stdin: TextIO = stdin
        self.stdout: TextIO = stdout
        self.stderr: TextIO = stderr
        self.status: int | None = None
        self.isatty: bool = stdout.isatty()
        self.pager: Pager | None = None

    @property
    @cache
    def repo(self):
        return Repository(self.dir / ".git")

    def edit_file(self, path: Path):
        editor = Editor.edit(path, self.editor_command())
        yield editor
        if not self.isatty:
            editor.close()

    def editor_command(self) -> str:
        core_editor = self.repo.config.get(["core", "editor"])
        git_editor = self.env.get("GIT_EDITOR")
        visual = self.env.get("VISUAL")
        editor = self.env.get("EDITOR")
        return git_editor or core_editor or visual or editor

    def setup_pager(self) -> None:
        if self.pager is not None:
            return

        if not self.stdout.isatty():
            return

        self.pager = Pager(self.env, self.stdout, self.stderr)
        assert self.stdout is not None
        self.stdout = self.pager.input

    def exit(self, status: int = 0) -> None:
        self.status = status
        raise ExitSignal(self.status)

    def execute(self) -> int:
        try:
            self.run()
            self.status = 0
        except ExitSignal as e:
            self.status = e.status

        if getattr(self, "pager", None) is not None:
            self.stdout.close()
            assert self.pager is not None
            self.pager.wait()

        assert self.status is not None
        return self.status

    def expanded_path(self, path: str) -> Path:
        return (self.dir / path).absolute()

    def fmt(self, style: str, string: str) -> str:
        return Color.format(style, string) if self.isatty else string

    def run(self) -> None:
        """Subclasses must override this."""
        raise NotImplementedError(f"{self.__class__.__name__}.run() not implemented")

    def println(self, string: str) -> None:
        try:
            self.stdout.write(string + "\n")
            self.stdout.flush()
        except BrokenPipeError:
            self.exit(0)


class ExitSignal(Exception):
    """Internal exception to short-circuit out of `run()` with a status."""

    def __init__(self, status: int = 0) -> None:
        super().__init__(f"Exit with status {status}")
        self.status: int | None = status
