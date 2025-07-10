from __future__ import annotations

import sys
from typing import TYPE_CHECKING, TextIO, Type, cast

from legit.pack_indexer import Indexer
from legit.pack_reader import Reader
from legit.pack_stream import Stream
from legit.pack_unpacker import Unpacker
from legit.progress import Progress
from legit.protocol import Remotes

if TYPE_CHECKING:
    from legit.repository import Repository


class RecvObjectsMixin:
    UNPACK_LIMIT: int = 100
    conn: Remotes.Protocol
    repo: Repository
    stderr: TextIO

    def recv_packed_objects(
        self, unpack_limit: int | None = None, prefix: bytes = b""
    ) -> None:
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

    def select_processor_class(
        self, reader: Reader, unpack_limit: int | None
    ) -> Type[Indexer | Unpacker]:
        if unpack_limit is None:
            unpack_limit = self.transfer_unpack_limit()

        if unpack_limit and reader.count > unpack_limit:
            return Indexer
        else:
            return Unpacker

    def transfer_unpack_limit(self) -> int:
        return (
            cast(int, self.repo.config.get(["transfer", "unpackLimit"]))
            or self.UNPACK_LIMIT
        )
