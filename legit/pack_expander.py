from io import BytesIO
from legit.numbers import VarIntLE
from legit.pack_delta import Delta
from legit.pack_stream import Stream


GIT_MAX_COPY = 0x10000


class Expander:
    def __init__(self, delta):
        self.delta = Stream(BytesIO(delta))
        self.source_size = self.read_size()
        self.target_size = self.read_size()

    @staticmethod
    def expand(source, delta):
        return Expander(delta)._expand(source)

    def _expand(self, source):
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

    def read_size(self):
        return VarIntLE.read(self.delta, 7)[1]

    def check_size(self, buffer, size):
        if len(buffer) != size:
            raise Exception("failed to apply delta")
