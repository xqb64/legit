import struct
from legit.numbers import PackedInt56LE, VarIntLE
from legit.pack_xdelta import XDelta


class Delta:
    class Copy:
        def __init__(self, offset: int, size: int):
            self.offset = offset
            self.size = size

        @classmethod
        def parse(cls, stream, byte: int) -> "Delta.Copy":
            value = PackedInt56LE.read(stream, byte)
            offset = value & 0xFFFFFFFF
            size = value >> 32
            return cls(offset, size)

        def to_bytes(self) -> bytes:
            value = (self.size << 32) | self.offset
            byte_array = PackedInt56LE.write(value)
            byte_array[0] |= 0x80
            return bytes(byte_array)

        def __eq__(self, other: object) -> bool:
            if not isinstance(other, Delta.Copy):
                return NotImplemented
            return self.offset == other.offset and self.size == other.size

        def __repr__(self) -> str:
            return f"Copy(offset={self.offset}, size={self.size})"

    class Insert:
        def __init__(self, data: bytes):
            self.data = data

        @classmethod
        def parse(cls, stream, byte: int) -> "Delta.Insert":
            return cls(stream.read(byte))

        def to_bytes(self) -> bytes:
            if not (0 < len(self.data) <= 127):
                raise ValueError("Insert data must be between 1 and 127 bytes.")
            return struct.pack(f"B{len(self.data)}s", len(self.data), self.data)

        def __eq__(self, other: object) -> bool:
            if not isinstance(other, Delta.Insert):
                return NotImplemented
            return self.data == other.data

        def __repr__(self) -> str:
            return f"Insert(data={self.data!r})"

    def __init__(self, source, target):
        self.base = source.entry if hasattr(source, "entry") else source

        data_parts = [self._sizeof(source), self._sizeof(target)]

        if source.delta_index is None:
            source.delta_index = XDelta.create_index(source.data)

        delta_ops = source.delta_index.compress(target.data)

        for op in delta_ops:
            data_parts.append(op.to_bytes())

        self.data = b"".join(data_parts)

    @property
    def size(self) -> int:
        return len(self.data)

    def _sizeof(self, entry) -> bytes:
        byte_array = VarIntLE.write(entry.size, 7)
        return bytes(byte_array)
