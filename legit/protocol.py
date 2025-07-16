from __future__ import annotations

import logging
import re
from typing import IO, Generator, Optional, cast

log = logging.getLogger(__name__)


class Remotes:
    class Protocol:
        def __init__(
            self,
            command: str,
            input_stream: IO[bytes],
            output_stream: IO[bytes],
            capabilities: Optional[list[str]] = None,
        ) -> None:
            self.command: str = command
            self.input: IO[bytes] = input_stream
            self.output: IO[bytes] = output_stream
            self.caps_local: list[str] = capabilities or []
            self.caps_remote: Optional[list[str]] = None
            self.caps_sent: bool = False

        def capable(self, ability: str) -> bool:
            return self.caps_remote is not None and ability in self.caps_remote

        def send_packet(self, line: Optional[str | bytes]) -> None:
            log.debug(f"send_packet got {line!r} to transmit")
            if line is None:
                self.output.write(b"0000")
                self.output.flush()
                return

            if isinstance(line, str):
                line = line.encode()

            line = self.append_caps(line)

            size = len(line) + 5
            header = f"{size:04x}".encode()

            self.output.write(header)
            self.output.write(line)
            self.output.write(b"\n")

            self.output.flush()

        def recv_packet(self) -> bytes | None:
            head = self.input.read(4)
            log.debug(f"recv_packet read: {head!r}")

            if not head:
                return None

            if not re.match(r"^[0-9a-f]{4}$".encode(), head, re.IGNORECASE):
                return head

            size = int(head, 16)
            if size == 0:
                return None

            body = self.input.read(size - 4)

            if body.endswith(b"\n"):
                body = body[:-1]

            return self.detect_caps(body)

        def recv_until(self, terminator: bytes | None) -> Generator[bytes]:
            while True:
                line = self.recv_packet()
                if line == terminator:
                    break
                yield cast(bytes, line)

        def append_caps(self, line: bytes) -> bytes:
            if self.caps_sent:
                return line
            self.caps_sent = True

            sep = "\0" if self.command != "fetch" else " "

            caps_to_send = set(x for x in self.caps_local)
            if self.caps_remote is not None:
                caps_to_send &= set(self.caps_remote)

            if not caps_to_send:
                return line

            return (
                line
                + sep.encode()
                + " ".join(sorted(list(x for x in caps_to_send))).encode()
            )

        def detect_caps(self, line: bytes) -> bytes:
            if self.caps_remote is not None:
                return line

            if self.command == "upload-pack":
                sep, n_fields = b" ", 3
            else:
                sep, n_fields = b"\0", 2

            parts = line.split(sep, n_fields - 1)

            if len(parts) == n_fields:
                caps_str = parts.pop()
            else:
                caps_str = b""

            self.caps_remote = (
                [cap.decode() for cap in re.split(rb" +", caps_str.strip())]
                if caps_str
                else []
            )

            return sep.join(parts)
