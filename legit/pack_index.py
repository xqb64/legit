from __future__ import annotations

import struct
from typing import BinaryIO

IDX_MAX_OFFSET: int = 0x80000000


class Index:
    HEADER_SIZE: int = 8
    FANOUT_SIZE: int = 1024

    OID_LAYER: int = 2
    CRC_LAYER: int = 3
    OFS_LAYER: int = 4
    EXT_LAYER: int = 5

    SIZES: dict[int, int] = {
        OID_LAYER: 20,
        CRC_LAYER: 4,
        OFS_LAYER: 4,
        EXT_LAYER: 8,
    }

    def __init__(self, _input: BinaryIO) -> None:
        self.input: BinaryIO = _input
        self.load_fanout_table()

    def load_fanout_table(self) -> None:
        self.input.seek(self.HEADER_SIZE)
        self.fanout = struct.unpack(">256I", self.input.read(self.FANOUT_SIZE))

    def oid_offset(self, oid: str) -> int | None:
        pos = self.oid_position(oid)
        if pos < 0:
            return None

        offset = self.read_int32(self.OFS_LAYER, pos)

        if offset < IDX_MAX_OFFSET:
            return offset

        pos = offset & (IDX_MAX_OFFSET - 1)

        self.input.seek(self.offset_for(self.EXT_LAYER, pos))
        data = self.input.read(8)
        return int.from_bytes(data, "big")

    def offset_for(self, layer: int, pos: int) -> int:
        offset = self.HEADER_SIZE + self.FANOUT_SIZE

        count = self.fanout[-1]

        for n, size in self.SIZES.items():
            if n < layer:
                offset += size * count

        return offset + pos * self.SIZES[layer]

    def read_int32(self, layer: int, pos: int) -> int:
        self.input.seek(self.offset_for(layer, pos))
        data = self.input.read(4)
        return int.from_bytes(data, "big")

    def oid_position(self, oid: str) -> int:
        prefix = int(oid[:2], 16)
        packed = bytes.fromhex(oid)

        low = 0 if prefix == 0 else self.fanout[prefix - 1]
        high = self.fanout[prefix] - 1

        return self.binary_search(packed, low, high)

    def binary_search(self, target: bytes, low: int, high: int) -> int:
        while low <= high:
            mid = (low + high) // 2

            self.input.seek(self.offset_for(self.OID_LAYER, mid))
            oid = self.input.read(20)

            if oid < target:
                low = mid + 1
            elif oid == target:
                return mid
            else:
                high = mid - 1

        return -1 - low

    def prefix_match(self, name: str) -> list[str]:
        pos = self.oid_position(name)
        if pos >= 0:
            return [name]

        self.input.seek(self.offset_for(self.OID_LAYER, -1 - pos))

        oids: list[str] = []

        while True:
            oid = self.input.read(20).hex()
            if not oid.startswith(name):
                return oids
            oids.append(oid)
