from __future__ import annotations

import os
import random
import string
from pathlib import Path
from typing import BinaryIO


class TempFile:
    TEMP_CHARS: str = string.ascii_lowercase + string.ascii_uppercase + string.digits

    def __init__(self, dirname: Path, prefix: str) -> None:
        self.dirname: Path = dirname
        self.path: Path = self.dirname / self.generate_temp_name(prefix)
        self.file: BinaryIO | None = None

    def generate_temp_name(self, prefix: str) -> str:
        return prefix + "".join(random.choices(self.TEMP_CHARS, k=6))

    def write(self, data: bytes) -> None:
        if self.file is None:
            self.open_file()
        assert self.file is not None
        self.file.write(data)

    def move(self, name: Path) -> None:
        assert self.file is not None
        self.file.close()
        os.rename(self.path, self.dirname / name)

    def open_file(self) -> None:
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
        mode = 0o644

        try:
            self.file = os.fdopen(os.open(self.path, flags, mode), "rb+")
        except FileNotFoundError:
            self.dirname.mkdir(exist_ok=True, parents=True)
            self.file = os.fdopen(os.open(self.path, flags, mode), "rb+")
