import sys

from legit.pack_stream import Stream
from legit.pack_reader import Reader
from legit.progress import Progress
from legit.pack_unpacker import Unpacker
from legit.pack_indexer import Indexer


class RecvObjectsMixin:
    def recv_packed_objects(self, unpack_limit=None, prefix: str = ''):
        stream = Stream(self.conn.input, prefix)
        reader = Reader(stream)
        if not self.conn.input is sys.stdin:
            progress = Progress(self.stderr)
        else:
            progress = None

        reader.read_header()

        factory = self.select_processor_class(reader, unpack_limit)
        processor = factory(self.repo.database, reader, stream, progress)

        processor.process_pack()
    
    def select_processor_class(self, reader, unpack_limit):
        if unpack_limit is None:
            unpack_limit = self.transfer_unpack_limit()

        if unpack_limit and reader.count > unpack_limit:
            return Indexer
        else:
            return Unpacker

    def transfer_unpack_limit(self):
        return self.repo.config.get(["tranfer", "unpackLimit"])
