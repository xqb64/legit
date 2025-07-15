from __future__ import annotations

import struct
import zlib
from typing import cast, reveal_type

from legit.numbers import VarIntBE, VarIntLE
from legit.pack import (
    BLOB,
    COMMIT,
    HEADER_FORMAT,
    HEADER_SIZE,
    OFS_DELTA,
    REF_DELTA,
    SIGNATURE,
    TREE,
    VERSION,
    InvalidPack,
    OfsDelta,
    Record,
    RefDelta,
)
from legit.pack_expander import Expander
from legit.pack_stream import Stream

TYPE_CODES_REVERSED: dict[int, str] = {COMMIT: "commit", BLOB: "blob", TREE: "tree"}


class Reader:
    def __init__(self, f: Stream) -> None:
        self.input: Stream = f
        self.count: int = 0

    def read_header(self) -> None:
        data = self.input.read(HEADER_SIZE)
        signature, version, self.count = struct.unpack(HEADER_FORMAT, data)

        if signature != SIGNATURE:
            raise InvalidPack(f"bad pack signature: {signature}")

        if version != VERSION:
            raise InvalidPack(f"unsupported pack version: {version}")

    def load_info(self) -> Record | OfsDelta | RefDelta | None:
        ty, size = self.read_record_header()

        if ty in [COMMIT, BLOB, TREE]:
            return Record(TYPE_CODES_REVERSED[ty], size)

        elif ty == OFS_DELTA:
            ofs_delta = self.read_ofs_delta()
            size = Expander(cast(bytes, ofs_delta.delta_data)).target_size

            return OfsDelta(ofs_delta.base_ofs, size)

        elif ty == REF_DELTA:
            ref_delta = self.read_ref_delta()
            size = Expander(cast(bytes, ref_delta.delta_data)).target_size

            return RefDelta(ref_delta.base_oid, size)

        else:
            return None

    def read_record(self) -> Record | OfsDelta | RefDelta:
        ty, _ = self.read_record_header()
        if ty in [COMMIT, BLOB, TREE]:
            decompressed_data = self.read_zlib_stream()
            return Record(TYPE_CODES_REVERSED[ty], decompressed_data)

        elif ty == OFS_DELTA:
            return self.read_ofs_delta()

        elif ty == REF_DELTA:
            return self.read_ref_delta()

        else:
            raise InvalidPack(f"Unknown pack object type: {ty}")

    def read_ofs_delta(self) -> OfsDelta:
        offset = VarIntBE.read(self.input)
        return OfsDelta(offset, self.read_zlib_stream())

    def read_ref_delta(self) -> RefDelta:
        base_oid = self.input.read(20).hex()
        delta_data = self.read_zlib_stream()
        return RefDelta(base_oid, delta_data)

    def read_record_header(self) -> tuple[int, int]:
        first, size = VarIntLE.read(self.input, 4)
        ty = (first >> 4) & 0x7
        return ty, size

    def read_zlib_stream(self) -> bytes:
        decompressor = zlib.decompressobj()
        output = bytearray()

        while not decompressor.eof:
            chunk = self.input.read_nonblock(256)

            try:
                output.extend(decompressor.decompress(chunk))
            except zlib.error as e:
                raise InvalidPack(f"Zlib decompression error: {e}") from e

        if decompressor.unused_data:
            self.input.seek(-len(decompressor.unused_data))

        output.extend(decompressor.flush())

        return bytes(output)
