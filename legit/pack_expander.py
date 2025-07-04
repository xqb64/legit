from io import StringIO
from legit.numbers import VarIntLE
from legit.pack_delta import Delta


class Expander:
    def __init__(self, delta):
        self.delta = StringIO(delta)
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
                target += source.encode()[copy.offset : copy.offset + copy.size]

    def read_size(self):
        return VarIntLE.read(self.delta, 7)[1]

    def check_size(self, buffer, size):
        if len(buffer.encode()) != size:
            raise Exception("failed to apply delta")
