import re
from datetime import datetime, timezone, timedelta
from typing import Optional


class Author:
    def __init__(self, name: str, email: str, time: datetime) -> None:
        self.name = name
        self.email = email
        self.time = time

    @classmethod
    def parse(cls, string: str) -> Optional["Author"]:
        parts = re.split(r"<|>", string)
        if len(parts) != 3:
            return None

        name, email, rest = (p.strip() for p in parts)
        try:
            epoch_str, offset_str = rest.split()
            epoch = int(epoch_str)
            sign = 1 if offset_str[0] == "+" else -1
            hours = int(offset_str[1:3])
            minutes = int(offset_str[3:5])
            tz = timezone(sign * timedelta(hours=hours, minutes=minutes))
            dt = datetime.fromtimestamp(epoch, tz)
        except Exception:
            return None

        return cls(name, email, dt)

    def readable_time(self) -> str:
        return self.time.strftime("%a %b %-d %H:%M:%S %Y %z")

    def short_date(self) -> str:
        return self.time.strftime("%Y-%m-%d")

    def __str__(self) -> str:
        epoch = int(self.time.timestamp())
        offset = self.time.strftime("%z")
        return f"{self.name} <{self.email}> {epoch} {offset}"
