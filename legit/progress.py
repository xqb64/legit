import time


UNITS = ["B", "KiB", "MiB", "GiB"]
SCALE = 1024.0


class Progress:
    def __init__(self, output):
        self.output = output
        self.message = None

    def start(self, message, total=None):
        if not self.output.isatty:
            return

        self.message = message
        self.total = total
        self.count = 0
        self.bytes = 0
        self.write_at = self.get_time()

    def get_time(self):
        return time.clock_gettime(time.CLOCK_MONOTONIC)

    def tick(self, _bytes=0):
        if not self.message:
            return

        self.count += 1
        self.bytes = _bytes

        current_time = self.get_time()
        if current_time < self.write_at + 0.05:
            return

        self.write_at = current_time
        self.clear_line()
        self.output.write(self.status_line())

    def stop(self):
        if not self.message:
            return

        self.total = self.count

        self.clear_line()
        self.output.write(self.status_line())

        self.message = None

    def clear_line(self):
        self.output.write("\x1b[G\x1b[K")
        self.output.flush()

    def status_line(self):
        line = f"{self.message}: {self.format_count()}"

        if self.bytes > 0:
            line += f", {self.format_bytes()}"

        if self.count == self.total:
            line += ", done."

        return line

    def format_count(self):
        if self.total:
            percent = 100 if self.total == 0 else 100 * self.count / self.total
            return f"{percent}% ({self.count} / {self.total})"
        else:
            return f"({self.count})"

    def format_bytes(self):
        import math

        power = math.floor(math.log(self.bytes, SCALE))
        scaled = self.bytes / (SCALE**power)

        return "%.2f %s" % (scaled, UNITS[power])
