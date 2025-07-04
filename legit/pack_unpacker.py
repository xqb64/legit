from legit.pack import Record, RefDelta
from legit.pack_expander import Expander


class Unpacker:
    def __init__(self, database, reader, stream, progress):
        self.database = database
        self.reader = reader
        self.stream = stream
        self.progress = progress

    def process_pack(self):
        if self.progress is not None:
            self.progress.start("Unpacking objects", self.reader.count)

        for n in range(self.reader.count):
            self.process_record()
            if self.progress is not None:
                self.progress.tick(self.stream.offset)
        
        if self.progress is not None:
            self.progress.stop()

        self.stream.verify_checksum()

    def process_record(self):
        with self.stream.capture():
            record, _ = self.reader.read_record()
            record = self.resolve(record)
            self.database.store(record)
    
    def resolve(self, record):
        if isinstance(record, Record):
            return record
        elif isinstance(record, RefDelta):
            return self.resolve_ref_delta(record)

    def resolve_ref_delta(self, delta):
        return self.resolve_delta(delta.base_oid, delta.delta_data)

    def resolve_delta(self, oid, delta_data):
        base = self.database.load_raw(oid)
        data = Expander.expand(base.data, delta_data)
        return Record(base.type(), data)
