from __future__ import annotations

from pathlib import Path

from legit.cmd_base import Base
from legit.config import ConfigFile
from legit.refs import Refs

DEFAULT_BRANCH = "master"


class Init(Base):
    def run(self) -> None:
        if self.args:
            root_path = Path(self.args[0]).absolute().resolve()
        else:
            root_path = Path(self.dir).absolute().resolve()

        git_path: Path = root_path / ".git"

        config = ConfigFile(git_path / "config")
        config.open_for_update()
        config.set(["core", "bare"], False)
        config.save()

        for d in ("objects", "refs/heads"):
            try:
                (git_path / d).mkdir(parents=True, exist_ok=True)
            except PermissionError as e:
                self.stderr.write(f"fatal: {e.strerror}")
                self.exit(1)

        refs = Refs(git_path)
        path = f"refs/heads/{DEFAULT_BRANCH}"
        refs.update_head(f"ref: {path}")

        self.println(f"Initialized empty Legit repository in {git_path}")
