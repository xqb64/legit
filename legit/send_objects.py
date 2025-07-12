from __future__ import annotations

from typing import TYPE_CHECKING, TextIO
import zlib

from legit.rev_list import RevList
from legit.pack_writer import Writer
from legit.progress import Progress


if TYPE_CHECKING:
    from legit.repository import Repository
    from legit.protocol import Remotes

class SendObjectsMixin:
    repo: Repository
    conn: Remotes.Protocol
    stderr: TextIO

    def send_packet_objects(self, revs: list[str]) -> None:
        rev_opts = {"objects": True, "missing": True}
        rev_list = RevList(self.repo, revs, rev_opts)

        pack_compression = (
            self.repo.config.get(["pack", "compression"])
            or self.repo.config.get(["core", "compression"])
            or zlib.Z_DEFAULT_COMPRESSION
        )

        write_opts = {
            "compression": pack_compression,
            "progress": Progress(self.stderr),
            "allow_ofs": self.conn.capable("ofs-delta"),
        }

        writer = Writer(self.conn.output, self.repo.database, write_opts)
        writer.write_objects(rev_list)

        self.conn.output.flush()
