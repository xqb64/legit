class VarIntLE:
    @staticmethod
    def write(value: int, shift) -> bytes:
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
    def read(stream, shift) -> tuple[int, int]:
        first = stream.readbyte()

        value = first & (2**shift - 1)
        shift = 4
        byte = first

        while byte >= 0x80:
            byte = stream.readbyte()
            value |= (byte & 0x7F) << shift
            shift += 7

        return first, value


class PackedInt56LE:
    @staticmethod
    def write(value: int):
        parts = [0]

        for i in range(7):
            byte = (value >> (8 * i)) & 0xFF
            if byte == 0:
                continue

            parts[0] |= 1 << i
            parts.append(byte)

        return parts

    @staticmethod
    def read(_input, header):
        value = 0

        for i in range(7):
            if (header & (1 << i)) == 0:
                continue

            value |= _input.readbyte() << (8 * i)

        return value
