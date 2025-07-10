from __future__ import annotations

from pathlib import Path
from typing import Sequence

from legit.config import ConfigFile, ConfigValue

GLOBAL_CONFIG = Path("~/.gitconfig").expanduser()
SYSTEM_CONFIG = Path("/etc/gitconfig")


class ConfigStack:
    def __init__(self, git_path: Path) -> None:
        self.configs = {
            "local": ConfigFile(git_path / "config"),
            "global": ConfigFile(GLOBAL_CONFIG),
            "system": ConfigFile(SYSTEM_CONFIG),
        }

    def file(self, name: str) -> ConfigFile:
        return self.configs.get(name) or ConfigFile(Path(name))

    def open(self) -> None:
        for cfg in self.configs.values():
            cfg.open()

    def get(self, key: Sequence[str]) -> ConfigValue | None:
        try:
            return self.get_all(key)[-1]
        except IndexError:
            return None

    def get_all(self, key: Sequence[str]) -> list[ConfigValue]:
        values: list[ConfigValue] = []
        for name in ("system", "global", "local"):
            cfg = self.configs[name]
            cfg.open()
            values.extend(cfg.get_all(key))
        return values
