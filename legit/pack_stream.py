import io
import os
import hashlib
from typing import Callable, Tuple, BinaryIO, Optional

from legit.pack import InvalidPack


class Stream:
    def __init__(self, inp: BinaryIO, buffer: bytes = b"") -> None:
        self.input: BinaryIO = inp
        self.digest = hashlib.sha1()
        self.offset = 0
        self.buffer = bytearray(buffer)
        self._capture: Optional[bytearray] = None

    def unread(self, data: bytes) -> None:
        if self._capture is not None:
            del self._capture[-len(data) :]
        self.buffer = bytearray(data) + self.buffer
        self.offset -= len(data)

    def capture(self, block: Callable[[], "T"]) -> Tuple["T", bytes]:
        self._capture = bytearray()
        try:
            result = block()
            return result, bytes(self._capture)
        finally:
            self.digest.update(self._capture)
            self._capture = None

    def verify_checksum(self) -> None:
        checksum_from_stream = self._read_buffered(20, block=True)
        if checksum_from_stream != self.digest.digest():
            raise InvalidPack("Checksum does not match value read from pack")


    def read(self, size: int) -> bytes:
        data = self._read_buffered(size, block=True)
        self._update_state(data)
        return data

    def read_nonblock(self, size: int) -> bytes:
        data = self._read_buffered(size, block=False)
        self._update_state(data)
        return data

    def readbyte(self) -> int:
        b = self.read(1)
        if not b:
            raise EOFError("Unexpected EOF when reading a byte")
        return b[0]

    def seek(self, amount: int, whence: int = os.SEEK_SET) -> None:
        if amount >= 0 or whence != os.SEEK_SET or self._capture is None:
            return

        bytes_to_unread = abs(amount)

        if bytes_to_unread > len(self._capture):
            raise ValueError(
                f"Cannot seek back {bytes_to_unread} bytes, only {len(self._capture)} available"
            )

        unread_data = self._capture[-bytes_to_unread:]
        del self._capture[-bytes_to_unread:]

        self.buffer = bytearray(unread_data) + self.buffer
        self.offset += amount

    def _read_buffered(self, size: int, block: bool = True) -> bytes:
        from_buf = bytes(self.buffer[:size])
        del self.buffer[: len(from_buf)]

        needed = size - len(from_buf)
        if needed <= 0:
            return from_buf

        try:
            chunk = self.input.read(needed)
            chunk = chunk or b""
            return from_buf + chunk

        except (EOFError, BlockingIOError):
            return from_buf

    def _update_state(self, data: bytes) -> None:
        self.offset += len(data)
        if self._capture is not None:
            self._capture.extend(data)
        else:
            self.digest.update(data)

    @property
    def eof(self) -> bool:
        if self.buffer:
            return False

        b = self.input.read(1)
        if not b:
            return True
        self.buffer.extend(b)
        return False

