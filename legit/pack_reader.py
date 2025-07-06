import zlib
import struct

from legit.pack import (
    OFS_DELTA,
    REF_DELTA,
    InvalidPack,
    HEADER_SIZE,
    HEADER_FORMAT,
    SIGNATURE,
    VERSION,
    COMMIT,
    BLOB,
    TREE,
    Record,
    RefDelta,
    OfsDelta,
)
from legit.numbers import VarIntBE, VarIntLE
from legit.pack_expander import Expander


TYPE_CODES_REVERSED = {COMMIT: "commit", BLOB: "blob", TREE: "tree"}


class Reader:
    def __init__(self, f):
        self.input = f
        self.count = 0

    def read_header(self):
        data = self.input.read(HEADER_SIZE)
        signature, version, self.count = struct.unpack(HEADER_FORMAT, data)

        if signature != SIGNATURE:
            raise InvalidPack(f"bad pack signature: {signature}")

        if version != VERSION:
            raise InvalidPack(f"unsupported pack version: {version}")

    def load_info(self):
        ty, size = self.read_record_header()

        if ty in [COMMIT, BLOB, TREE]:
            return Record(TYPE_CODES_REVERSED[ty], size)
    
        elif ty == OFS_DELTA:
            delta = self.read_ofs_delta()
            size = Expander.expand(delta.delta_data).target_size

            return OfsDelta(delta.base_ofs, size)

        elif ty == REF_DELTA:
            delta = self.read_ref_delta()
            size = Expander(delta.delta_data).target_size

            return RefDelta(delta.base_oid, size)

    def read_record(self) -> "Record | None":
        ty, _ = self.read_record_header()

        if ty in [COMMIT, BLOB, TREE]:
            decompressed_data = self.read_zlib_stream()
            return Record(TYPE_CODES_REVERSED.get(ty), decompressed_data)

        elif ty == OFS_DELTA:
            return self.read_ofs_delta() 

        elif ty == REF_DELTA:
            return self.read_ref_delta()

        else:
            raise InvalidPack(f"Unknown pack object type: {ty}")

    def read_ofs_delta(self):
        offset = VarIntBE.read(self.input)
        return OfsDelta(offset, self.read_zlib_stream())

    def read_ref_delta(self):
        base_oid = self.input.read(20).hex()
        delta_data = self.read_zlib_stream()
        return RefDelta(base_oid, delta_data)

    def read_record_header(self):
        byte, size = VarIntLE.read(self.input, 4)
        ty = (byte >> 4) & 0x7
        return ty, size

    def read_zlib_stream(self) -> bytes:
        decompressor = zlib.decompressobj()
        output = bytearray()

        while not decompressor.eof:
            chunk = self.input.read_nonblock(256)
            if not chunk and not decompressor.eof:
                raise InvalidPack(
                    "Input stream ended unexpectedly during zlib decompression"
                )

            try:
                output.extend(decompressor.decompress(chunk))
            except zlib.error as e:
                raise InvalidPack(f"Zlib decompression error: {e}") from e

        # After the loop, decompressor.unused_data holds the over-read bytes.
        # We use our custom Stream's seek method to "un-read" this data by
        # prepending it to the internal buffer for the next read operation.
        if decompressor.unused_data:
            # A negative seek on our Stream wrapper moves data back to the buffer.
            self.input.seek(-len(decompressor.unused_data))

        return bytes(output)
