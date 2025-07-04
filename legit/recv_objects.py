import sys

from legit.pack_stream import Stream
from legit.pack_reader import Reader
from legit.progress import Progress


class RecvObjectsMixin:
    def recv_packed_objects(self, prefix: str = ''):
        stream = Stream(self.conn.input, prefix)
        reader = Reader(stream)
        if not self.conn.input is sys.stdin:
            progress = Progress(self.stderr)
        else:
            progress = None

        reader.read_header()

        unpacker = Unpacker(self.repo.database, reader, stream, progress)
        unpacker.process_pack()

