from __future__ import annotations

import hashlib
import struct
import zlib
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Optional, cast

from legit.pack import (
    HEADER_FORMAT,
    IDX_MAX_OFFSET,
    IDX_SIGNATURE,
    SIGNATURE,
    VERSION,
    OfsDelta,
    Record,
    RefDelta,
)
from legit.pack_expander import Expander
from legit.pack_reader import Reader
from legit.pack_stream import Stream
from legit.temp_file import TempFile

if TYPE_CHECKING:
    from legit.database import Database
    from legit.progress import Progress


class Indexer:
    def __init__(
        self,
        database: Database,
        reader: Reader,
        stream: Stream,
        progress: Optional[Progress],
    ) -> None:
        self.database: Database = database
        self.reader: Reader = reader
        self.stream: Stream = stream
        self.progress: Optional[Progress] = progress

        self.index: dict[str, list[int]] = {}

        self.pending: defaultdict[int | str, list[list[int]]] = defaultdict(
            list[list[int]]
        )

        self.pack_file: PackFile = PackFile(self.database.pack_path, "tmp_pack")
        self.index_file: PackFile = PackFile(self.database.pack_path, "tmp_idx")

    def process_pack(self) -> None:
        self.write_header()
        self.write_objects()
        self.write_checksum()

        self.resolve_deltas()

        self.write_index()

    def write_header(self) -> None:
        header = struct.pack(HEADER_FORMAT, SIGNATURE, VERSION, self.reader.count)
        self.pack_file.write(header)

    def write_objects(self) -> None:
        if self.progress is not None:
            self.progress.start("Receiving objects", self.reader.count)

        for n in range(self.reader.count):
            self.index_object()

            if self.progress is not None:
                self.progress.tick(self.stream.offset)

        if self.progress is not None:
            self.progress.stop()

    def index_object(self) -> None:
        offset = self.stream.offset
        record, data = self.stream.capture(lambda: self.reader.read_record())

        crc32 = zlib.crc32(data)
        self.pack_file.write(data)

        if isinstance(record, Record):
            oid = self.database.hash_object(record)
            self.index[oid] = [offset, crc32]
        elif isinstance(record, OfsDelta):
            self.pending[offset - record.base_ofs].append([offset, crc32])
        elif isinstance(record, RefDelta):
            self.pending[record.base_oid].append([offset, crc32])

    def write_checksum(self) -> None:
        self.stream.verify_checksum()

        filename = f"pack-{self.pack_file.digest.hexdigest()}.pack"
        self.pack_file.move(Path(filename))

        path = self.database.pack_path / filename
        self.pack = open(path, "rb")

        pack_stream = Stream(self.pack)
        self.reader = Reader(pack_stream)

    def read_record_at(self, offset: int) -> Record | OfsDelta | RefDelta:
        self.pack.seek(offset)
        return self.reader.read_record()

    def resolve_deltas(self) -> None:
        deltas = sum(len(list_) for _, list_ in self.pending.items())
        if self.progress is not None:
            self.progress.start("Resolving deltas", deltas)

        for oid, (offset, _) in list(self.index.items()):
            record = cast(Record, self.read_record_at(offset))
            self.resolve_delta_base(record, offset)
            self.resolve_delta_base(record, oid)

        if self.progress is not None:
            self.progress.stop()

    def resolve_delta_base(self, record: Record, oid: str | int) -> None:
        if not (pending := self.pending.pop(oid, None)):
            return

        for offset, crc32 in pending:
            self.resolve_pending(record, offset, crc32)

    def resolve_pending(self, record: Record, offset: int, crc32: int) -> None:
        delta = cast(OfsDelta | RefDelta, self.read_record_at(offset))
        data = Expander.expand(cast(bytes, record.data), cast(bytes, delta.delta_data))
        obj = Record(record.ty, data)
        oid = self.database.hash_object(obj)

        self.index[oid] = [offset, crc32]

        if self.progress is not None:
            self.progress.tick()

        self.resolve_delta_base(obj, offset)
        self.resolve_delta_base(obj, oid)

    def write_index(self) -> None:
        self.object_ids = sorted(self.index.keys())

        self.write_object_table()
        self.write_crc32()
        self.write_offsets()
        self.write_index_checksum()

    def write_object_table(self) -> None:
        header = struct.pack(">II", IDX_SIGNATURE, VERSION)
        self.index_file.write(header)

        counts = [0 for _ in range(256)]
        total = 0

        for oid in self.object_ids:
            counts[int(oid[:2], 16)] += 1

        for count in counts:
            total += count
            self.index_file.write(struct.pack(">I", total))

        for oid in self.object_ids:
            self.index_file.write(struct.pack(">20s", bytes.fromhex(oid)))

    def write_crc32(self) -> None:
        for oid in self.object_ids:
            crc32 = self.index[oid][-1]
            self.index_file.write(struct.pack(">I", crc32))

    def write_offsets(self) -> None:
        large_offsets = []

        for oid in self.object_ids:
            offset = self.index[oid][0]

            if offset >= IDX_MAX_OFFSET:
                large_offsets.append(offset)
                offset = IDX_MAX_OFFSET | (len(large_offsets) - 1)

            self.index_file.write(struct.pack(">I", offset))

        for offset in large_offsets:
            self.index_file.write(struct.pack("Q>", offset))

    def write_index_checksum(self) -> None:
        pack_digest = self.pack_file.digest
        self.index_file.write(pack_digest.digest())

        filename = f"pack-{pack_digest.hexdigest()}.idx"
        self.index_file.move(Path(filename))


class PackFile:
    def __init__(self, pack_dir: Path, name: str) -> None:
        pack_dir.mkdir(exist_ok=True, parents=True)
        self.file = TempFile(pack_dir, name)
        self.digest = hashlib.sha1()

    def write(self, data: bytes) -> None:
        self.file.write(data)
        self.digest.update(data)

    def move(self, name: Path) -> None:
        self.file.write(self.digest.digest())
        self.file.move(name)
