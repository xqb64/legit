from __future__ import annotations

import math
import time
from typing import TextIO

UNITS = ["B", "KiB", "MiB", "GiB"]
SCALE = 1024.0


class Progress:
    def __init__(self, output: TextIO) -> None:
        self.output = output
        self.message: str | None = None

    def start(self, message: str, total: int | None = None) -> None:
        if not self.output.isatty():
            return

        self.message = message
        self.total = total
        self.count = 0
        self.bytes = 0
        self.write_at = self.get_time()

    def get_time(self) -> float:
        return time.clock_gettime(time.CLOCK_MONOTONIC)

    def tick(self, _bytes: int = 0) -> None:
        if not self.message:
            return

        self.count += 1
        self.bytes = _bytes

        current_time = self.get_time()
        if current_time < self.write_at + 0.01:
            return

        self.write_at = current_time
        self.clear_line()
        self.output.write(self.status_line())
        self.output.flush()

    def stop(self) -> None:
        if not self.message:
            return

        self.total = self.count

        self.clear_line()
        self.output.write(self.status_line())
        self.output.flush()

        self.message = None

    def clear_line(self) -> None:
        self.output.write("\x1b[G\x1b[K")
        self.output.flush()

    def status_line(self) -> str:
        line = f"{self.message}: {self.format_count()}"

        if self.bytes > 0:
            line += f", {self.format_bytes()}"

        if self.count == self.total:
            line += ", done.\n"

        return line

    def format_count(self) -> str:
        if self.total:
            percent = 100 if self.total == 0 else 100 * self.count / self.total
            return f"{percent:.2f}% ({self.count} / {self.total})"
        else:
            return f"({self.count})"

    def format_bytes(self) -> str:
        power = math.floor(math.log(self.bytes, SCALE))
        scaled = self.bytes / (SCALE**power)
        return "%.2f %s" % (scaled, UNITS[power])
