import zlib
import hashlib
import struct
import sys

from legit.pack import HEADER_FORMAT, SIGNATURE, VERSION
from legit.numbers import VarIntLE
from legit.pack_entry import Entry
from legit.pack_compressor import Compressor


class Writer:
    def __init__(self, output, database, options={}):
        self.output = output
        self.digest = hashlib.sha1()
        self.database = database
        self.compression = options.get("compression", zlib.Z_DEFAULT_COMPRESSION)
        self.progress = options.get("progress")
        self.allow_ofs = options.get("allow_ofs")
        self.offset = 0

    def write_objects(self, rev_list):
        self.prepare_pack_list(rev_list)
        self.compress_objects()
        self.write_header()
        self.write_entries()
        self.output.write(self.digest.digest())

    def compress_objects(self):
        compressor = Compressor(self.database, self.progress)
        for entry in self.pack_list:
            compressor.add(entry)
        compressor.build_deltas()

    def write(self, data: bytes):
        self.output.write(data)
        self.output.flush()
        self.digest.update(data)
        self.offset += len(data)

    def prepare_pack_list(self, rev_list):
        self.pack_list = []

        if self.progress is not None:
            self.progress.start("Counting objects")

        for obj, path in rev_list:
            self.add_to_pack_list(obj, path)

            if self.progress is not None:
                self.progress.tick()

        if self.progress is not None:
            self.progress.stop()

    def add_to_pack_list(self, obj, path):
        info = self.database.load_info(obj.oid)
        self.pack_list.append(Entry(obj.oid, info, path, self.allow_ofs))

    def write_header(self):
        header = struct.pack(HEADER_FORMAT, SIGNATURE, VERSION, len(self.pack_list))
        self.write(header)

    def write_entries(self):
        count = len(self.pack_list)

        if self.progress is not None:
            if self.output is not sys.stdout:
                self.progress.start("Writing objects", count)

        for entry in self.pack_list:
            self.write_entry(entry)

        if self.progress is not None:
            self.progress.stop()

    def write_entry(self, entry: "Writer.Entry"):
        if entry.delta:
            self.write_entry(entry.delta.base)

        if entry.offset:
            return

        entry.offset = self.offset

        obj = entry.delta or self.database.load_raw(entry.oid)

        header = VarIntLE.write(entry.packed_size, 4)
        header_list = list(header)
        header_list[0] |= entry.packed_type << 4
        self.write(bytes(header_list))
        self.write(entry.delta_prefix)
        compressed = zlib.compress(obj.data, self.compression)
        self.write(compressed)

        if self.progress is not None:
            self.progress.tick(self.offset)
