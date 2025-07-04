import os
import string
import random


class TempFile:
    TEMP_CHARS = string.ascii_lowercase + string.ascii_uppercase + string.digits

    def __init__(self, dirname, prefix):
        self.dirname = dirname
        self.path = self.dirname / self.generate_temp_name(prefix)
        self.file = None

    def generate_temp_name(self, prefix: str) -> str:
        return prefix + "".join(random.choices(self.TEMP_CHARS, k=6))

    def write(self, data) -> None:
        if self.file is None:
            self.open_file()
        self.file.write(data)

    def move(self, name) -> None:
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
