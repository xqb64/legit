from __future__ import annotations

from io import BytesIO

from legit.numbers import VarIntLE
from legit.pack_delta import Delta
from legit.pack_stream import Stream

GIT_MAX_COPY: int = 0x10000


class Expander:
    def __init__(self, delta: bytes) -> None:
        self.delta = Stream(BytesIO(delta))
        self.source_size: int = self.read_size()
        self.target_size: int = self.read_size()

    @staticmethod
    def expand(source: bytes, delta: bytes) -> bytes:
        return Expander(delta)._expand(source)

    def _expand(self, source: bytes) -> bytes:
        self.check_size(source, self.source_size)
        target = b""

        while not self.delta.eof:
            byte = self.delta.readbyte()

            if byte < 0x80:
                insert = Delta.Insert.parse(self.delta, byte)
                target += insert.data
            else:
                copy = Delta.Copy.parse(self.delta, byte)
                size = copy.size if copy.size != 0 else GIT_MAX_COPY
                target += source[copy.offset : copy.offset + size]

        self.check_size(target, self.target_size)
        return target

    def read_size(self) -> int:
        return VarIntLE.read(self.delta, 7)[1]

    def check_size(self, buffer: bytes, size: int) -> None:
        if len(buffer) != size:
            raise Exception("failed to apply delta")
