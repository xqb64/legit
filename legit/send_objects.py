import zlib

from legit.rev_list import RevList
from legit.pack_writer import Writer
from legit.progress import Progress


class SendObjectsMixin:
    def send_packet_objects(self, revs):
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
        }
        writer = Writer(self.conn.output, self.repo.database, write_opts)

        writer.write_objects(rev_list)
