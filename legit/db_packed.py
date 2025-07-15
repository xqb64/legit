from __future__ import annotations

from pathlib import Path
from typing import BinaryIO, cast, reveal_type

from legit.db_loose import Raw
from legit.pack import OfsDelta, Record, RefDelta
from legit.pack_expander import Expander
from legit.pack_index import Index
from legit.pack_reader import Reader
from legit.pack_stream import Stream


class Packed:
    def __init__(self, path: Path) -> None:
        self.pack_file_handle: BinaryIO = open(path, "rb")
        self.pack_file: Stream = Stream(self.pack_file_handle)
        self.reader: Reader = Reader(self.pack_file)

        self.index_file_handle: BinaryIO = open(path.with_suffix(".idx"), "rb")
        self.index: Index = Index(self.index_file_handle)

    def close(self) -> None:
        self.pack_file_handle.close()
        self.index_file_handle.close()

    def __del__(self) -> None:
        self.close()

    def prefix_match(self, name: str) -> list[str]:
        return self.index.prefix_match(name)

    def has(self, oid: str) -> bool:
        return self.index.oid_offset(oid) is not None

    def load_raw(self, oid: str) -> Record | OfsDelta | RefDelta | None:
        offset = self.index.oid_offset(oid)
        if offset is not None:
            return self.load_raw_at(offset)
        else:
            return None

    def load_raw_at(self, offset: int) -> Record | OfsDelta | RefDelta | None:
        self.pack_file_handle.seek(offset)
        record = self.reader.read_record()

        if isinstance(record, Record):
            return record

        elif isinstance(record, OfsDelta):
            base = self.load_raw_at(offset - record.base_ofs)
            return self.expand_delta(cast(Record, base), record)

        elif isinstance(record, RefDelta):
            base = self.load_raw(record.base_oid)
            return self.expand_delta(cast(Record, base), record)

        else:
            return None

    def expand_delta(self, base: Record, record: OfsDelta | RefDelta) -> Record:
        data = Expander.expand(cast(bytes, base.data), cast(bytes, record.delta_data))
        return Record(base.ty, data)

    def load_info(self, oid: str) -> Raw | None:
        offset = self.index.oid_offset(oid)
        if offset is not None:
            return self.load_info_at(offset)
        return None

    def load_info_at(self, offset: int) -> Raw | None:
        self.pack_file_handle.seek(offset)
        record = self.reader.load_info()

        if isinstance(record, Record):
            return Raw(record.ty, cast(int, record.data), None)

        elif isinstance(record, OfsDelta):
            base = self.load_info_at(offset - record.base_ofs)
            assert base is not None
            return Raw(base.ty, cast(int, record.delta_data), None)

        elif isinstance(record, RefDelta):
            base = self.load_info(record.base_oid)
            assert base is not None
            return Raw(base.ty, cast(int, record.delta_data), None)

        else:
            return None
