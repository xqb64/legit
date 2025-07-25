from __future__ import annotations


from legit.pack_stream import Stream


class VarIntLE:
    @staticmethod
    def write(value: int, shift: int) -> bytes:
        parts = []
        mask = 2**shift - 1

        while value > mask:
            parts.append(0x80 | (value & mask))
            value >>= shift
            mask = 0x7F
            shift = 7

        parts.append(value)
        return bytes(parts)

    @staticmethod
    def read(stream: Stream, shift: int) -> tuple[int, int]:
        first = stream.readbyte()

        value = first & (2**shift - 1)
        byte = first

        while byte >= 0x80:
            byte = stream.readbyte()
            value |= (byte & 0x7F) << shift
            shift += 7

        return first, value


class VarIntBE:
    @staticmethod
    def write(value: int) -> bytes:
        _bytes = [value & 0x7F]
        value >>= 7
        while value != 0:
            value -= 1
            _bytes.append(0x80 | value & 0x7F)
            value >>= 7

        return bytes(reversed(_bytes))

    @staticmethod
    def read(stream: Stream) -> int:
        byte = stream.readbyte()
        value = byte & 0x7F

        while byte >= 0x80:
            byte = stream.readbyte()
            value = ((value + 1) << 7) | (byte & 0x7F)

        return value


class PackedInt56LE:
    @staticmethod
    def write(value: int) -> list[int]:
        parts = [0]

        for i in range(7):
            byte = (value >> (8 * i)) & 0xFF
            if byte == 0:
                continue

            parts[0] |= 1 << i
            parts.append(byte)

        return parts

    @staticmethod
    def read(stream: Stream, header: int) -> int:
        value = 0

        for i in range(7):
            if (header & (1 << i)) == 0:
                continue

            value |= stream.readbyte() << (8 * i)

        return value
