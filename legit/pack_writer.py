from __future__ import annotations

import hashlib
import struct
import sys
import zlib
from io import BytesIO
from pathlib import Path
from typing import IO, Any, Optional, cast

from legit.database import Database
from legit.db_entry import DatabaseEntry
from legit.db_loose import Raw
from legit.numbers import VarIntLE
from legit.pack import HEADER_FORMAT, SIGNATURE, VERSION
from legit.pack_compressor import Compressor
from legit.pack_entry import Entry
from legit.rev_list import RevList


class Writer:
    def __init__(
        self,
        output: IO[bytes],
        database: Database,
        options: Optional[dict[str, Any]] = None,
    ):
        options = options or {}
        self.output: IO[bytes] = output
        self.digest = hashlib.sha1()
        self.database = database
        self.compression = options.get("compression", zlib.Z_DEFAULT_COMPRESSION)
        self.progress = options.get("progress")
        self.allow_ofs: bool = cast(bool, options.get("allow_ofs"))
        self.offset = 0

    def write_objects(self, rev_list: RevList) -> None:
        self.prepare_pack_list(rev_list)
        self.compress_objects()
        self.write_header()
        self.write_entries()
        self.output.write(self.digest.digest())

    def compress_objects(self) -> None:
        compressor = Compressor(self.database, self.progress)
        for entry in self.pack_list:
            compressor.add(entry)
        compressor.build_deltas()

    def write(self, data: bytes) -> None:
        self.output.write(data)
        self.output.flush()
        self.digest.update(data)
        self.offset += len(data)

    def prepare_pack_list(self, rev_list: RevList) -> None:
        self.pack_list: list[Entry] = []

        if self.progress is not None:
            self.progress.start("Counting objects")

        for obj, path in rev_list:
            self.add_to_pack_list(cast(DatabaseEntry, obj), path)

            if self.progress is not None:
                self.progress.tick()

        if self.progress is not None:
            self.progress.stop()

    def add_to_pack_list(self, obj: DatabaseEntry, path: Optional[Path]) -> None:
        info = self.database.load_info(obj.oid)
        self.pack_list.append(Entry(obj.oid, info, path, self.allow_ofs))

    def write_header(self) -> None:
        header = struct.pack(HEADER_FORMAT, SIGNATURE, VERSION, len(self.pack_list))
        self.write(header)

    def write_entries(self) -> None:
        count = len(self.pack_list)

        if self.progress is not None:
            if self.output is not sys.stdout:
                self.progress.start("Writing objects", count)

        for entry in self.pack_list:
            self.write_entry(entry)

        if self.progress is not None:
            self.progress.stop()

    def write_entry(self, entry: Entry) -> None:
        if entry.delta:
            self.write_entry(cast(Entry, entry.delta.base))

        if entry.offset:
            return

        entry.offset = self.offset

        obj = entry.delta or cast(Raw, self.database.load_raw(entry.oid))

        header = VarIntLE.write(entry.packed_size, 4)
        header_list = list(header)
        header_list[0] |= entry.packed_type << 4
        self.write(bytes(header_list))
        self.write(entry.delta_prefix)
        compressed = zlib.compress(cast(bytes, obj.data), self.compression)
        self.write(compressed)

        if self.progress is not None:
            self.progress.tick(self.offset)

        return None
