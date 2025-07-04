import struct
from legit.numbers import PackedInt56LE, VarIntLE
from legit.pack_xdelta import XDelta


class Delta:
    """
    Represents the difference between two objects (a "delta").
    The data is stored in a format compatible with Git's packfiles.
    """

    class Copy:
        """Represents a 'copy' instruction in a delta."""

        def __init__(self, offset: int, size: int):
            self.offset = offset
            self.size = size

        @classmethod
        def parse(cls, stream, byte: int) -> "Delta.Copy":
            """Parses a copy instruction from a byte stream."""
            value = PackedInt56LE.read(stream, byte)
            offset = value & 0xFFFFFFFF
            size = value >> 32
            return cls(offset, size)

        def to_bytes(self) -> bytes:
            """Encodes the copy instruction to bytes."""
            # Combine size and offset into a 56-bit integer
            value = (self.size << 32) | self.offset
            byte_array = PackedInt56LE.write(value)
            # Set the most significant bit of the first byte to 1
            byte_array[0] |= 0x80
            return bytes(byte_array)

        def __repr__(self) -> str:
            return f"Copy(offset={self.offset}, size={self.size})"

    class Insert:
        """Represents an 'insert' instruction in a delta."""

        def __init__(self, data: bytes):
            self.data = data

        @classmethod
        def parse(cls, stream, byte: int) -> "Delta.Insert":
            """Parses an insert instruction from a byte stream."""
            # The 'byte' indicates the length of the data to read
            return cls(stream.read(byte))

        def to_bytes(self) -> bytes:
            """Encodes the insert instruction to bytes."""
            # The format is [1-byte length][data]
            if not (0 < len(self.data) <= 127):
                raise ValueError("Insert data must be between 1 and 127 bytes.")
            return struct.pack(f"B{len(self.data)}s", len(self.data), self.data)

        def __repr__(self) -> str:
            return f"Insert(data={self.data!r})"

    def __init__(self, source, target):
        """
        Initializes and computes the delta between a source and target object.

        Args:
            source: The base object (Unpacked).
            target: The target object to be expressed as a delta (Unpacked).
        """
        self.base = source.entry if hasattr(source, "entry") else source

        # The delta data starts with the varint-encoded sizes of the source and target
        data_parts = [self._sizeof(source), self._sizeof(target)]

        # Lazily create and cache the delta index on the source object
        if source.delta_index is None:
            source.delta_index = XDelta.create_index(source.data)

        # Use the index to find differences and generate delta operations
        delta_ops = source.delta_index.compress(target.data)

        # Convert each operation (Copy/Insert) to its byte representation
        for op in delta_ops:
            data_parts.append(op.to_bytes())

        self.data = b"".join(data_parts)

    @property
    def size(self) -> int:
        """Returns the total size of the delta data in bytes."""
        return len(self.data)

    def _sizeof(self, entry) -> bytes:
        """(Private) Encodes an object's size as a VarIntLE byte string."""
        byte_array = VarIntLE.write(entry.size, 7)
        return bytes(byte_array)
