from __future__ import annotations

from typing import TYPE_CHECKING, cast

from legit.pack import OfsDelta, Record, RefDelta
from legit.pack_expander import Expander

if TYPE_CHECKING:
    from legit.database import Database
    from legit.pack_reader import Reader
    from legit.pack_stream import Stream
    from legit.progress import Progress


class Unpacker:
    def __init__(
        self,
        database: Database,
        reader: Reader,
        stream: Stream,
        progress: Progress | None,
    ) -> None:
        self.database = database
        self.reader = reader
        self.stream = stream
        self.progress = progress
        self.offsets: dict[int, str] = {}

    def process_pack(self) -> None:
        if self.progress is not None:
            self.progress.start("Unpacking objects", self.reader.count)

        for n in range(self.reader.count):
            self.process_record()
            if self.progress is not None:
                self.progress.tick(self.stream.offset)

        if self.progress is not None:
            self.progress.stop()

        self.stream.verify_checksum()

    def process_record(self) -> None:
        offset = self.stream.offset
        record, data = self.stream.capture(lambda: self.reader.read_record())
        assert record is not None
        record = self.resolve(record, offset)
        if record is not None:
            self.database.store(record)
            assert record.oid is not None
            self.offsets[offset] = record.oid

    def resolve(self, record: Record | OfsDelta | RefDelta, offset: int) -> Record:
        if isinstance(record, Record):
            return record
        elif isinstance(record, OfsDelta):
            return self.resolve_ofs_delta(record, offset)
        elif isinstance(record, RefDelta):
            return self.resolve_ref_delta(record)

    def resolve_ofs_delta(self, delta: OfsDelta, offset: int) -> Record:
        oid = self.offsets[offset - delta.base_ofs]
        return self.resolve_delta(oid, cast(bytes, delta.delta_data))

    def resolve_ref_delta(self, delta: RefDelta) -> Record:
        return self.resolve_delta(delta.base_oid, cast(bytes, delta.delta_data))

    def resolve_delta(self, oid: str, delta_data: bytes) -> Record:
        base = cast(Record, self.database.load_raw(oid))
        data = Expander.expand(cast(bytes, base.data), delta_data)
        return Record(base.ty, data)
