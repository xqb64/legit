import io
import zlib
import struct

from legit.pack import REF_DELTA, InvalidPack, HEADER_SIZE, HEADER_FORMAT, SIGNATURE, VERSION, TYPE_CODES, COMMIT, BLOB, TREE, Record, RefDelta
from legit.numbers import VarIntLE
from legit.pack_expander import Expander


TYPE_CODES_REVERSED = {
    COMMIT: "commit",
    BLOB: "blob",
    TREE: "tree"
}


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

        if ty == REF_DELTA:
            delta = self.read_ref_delta()
            size = Expander(delta.delta_data).target_size

            return RefDelta(delta.base_oid, size)

    def read_record(self) -> 'Record | None':
        ty, _ = self.read_record_header()

        if ty in [COMMIT, BLOB, TREE]:
            decompressed_data = self.read_zlib_stream()
            return Record(TYPE_CODES_REVERSED.get(ty), decompressed_data)

        elif ty == 7:
            return self.read_ref_delta()

        elif ty == 6:
            # Skip the variable-length offset
            byte = self.input.readbyte()
            while byte & 0x80:
                byte = self.input.readbyte()
            
            # Skip the zlib-compressed delta data
            self.read_zlib_stream() 
            
            # Return None to indicate the object was skipped
            return None

        else:
            raise InvalidPack(f"Unknown pack object type: {ty}")

    def read_ref_delta(self):
        base_oid = self.input.read(20).hex()
        delta_data = self.read_zlib_stream()
        return RefDelta(base_oid, delta_dat)
    
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
                raise InvalidPack("Input stream ended unexpectedly during zlib decompression")
            
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


