from legit.pack import Record, RefDelta
from legit.pack_expander import Expander
from legit.pack_reader import Reader
from legit.pack_index import Index
from legit.db_loose import Raw


class Packed:
    def __init__(self, path):
        self.pack_file = open(path, "rb")
        self.reader = Reader(self.pack_file)

        self.index_file = open(path.with_suffix(".idx"), "rb")
        self.index = Index(self.index_file)

    def prefix_match(self, name: str) -> list[str]:
        return self.index.prefix_match(name)

    def has(self, oid: str) -> bool:
        return self.index.oid_offset(oid) is not None

    def load_raw(self, oid: str):
        offset = self.index.oid_offset(oid)
        if offset:
            return self.load_raw_at(offset)
        else:
            return None

    def load_raw_at(self, offset):
        self.pack_file.seek(offset)
        record = self.reader.read_record()

        if isinstance(record, Record):
            return record
        elif isinstance(record, RefDelta):
            base = self.load_raw(record.base_oid)
            return self.expand_delta(base, record)

    def expand_delta(self, base, record):
        data = Expander.expand(base.data, record.delta_data)
        return Record(base.ty, data)

    def load_info(self, oid: str):
        offset = self.index.oid_offset(oid)
        if offset:
            return self.load_info_at(offset)
        return None

    def load_info_at(self, offset):
        self.pack_file.seek(offset)
        record = self.reader.read_info()

        if isinstance(record, Record):
            return Raw(record.ty, record.data, None)
        elif isinstance(record, RefDelta):
            base = self.load_info(record.base_oid)
            return Raw(base.ty, record.delta_data, None)

