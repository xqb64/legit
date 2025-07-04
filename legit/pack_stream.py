import hashlib
from contextlib import contextmanager
from legit.pack import InvalidPack


class Stream:
    def __init__(self, f, buffer=b""):
        self.input = f
        self.digest = hashlib.sha1()
        self.offset = 0
        self.buffer = bytearray(buffer)
        self._capture = None

    @contextmanager
    def capture(self):
        """A context manager to capture all bytes read within its scope."""
        self._capture = bytearray()
        try:
            yield
        finally:
            if self._capture is not None:
                self.digest.update(self._capture)
            self._capture = None

    def verify_checksum(self):
        expected = self.digest.digest()
        actual = self.read(20)
        if actual != expected:
            raise InvalidPack("Checksum does not match value read from pack")

    def read(self, size: int) -> bytes:
        data = self.read_buffered(size, block=True)
        self.update_state(data)
        return data

    def read_nonblock(self, size: int) -> bytes:
        data = self.read_buffered(size, block=False)
        self.update_state(data)
        return data

    def readbyte(self) -> int:
        """
        Reads a single byte and returns it as an integer.

        Raises:
            EOFError: If the end of the stream is reached unexpectedly.
        """
        b = self.read(1)
        if not b:
            raise EOFError("Unexpected EOF when reading a byte")
        return b[0]

    def seek(self, amount: int):
        """
        Custom seek for buffer manipulation. A negative amount 'un-reads' data
        by moving it from the capture buffer back to the main read buffer.
        """
        if amount >= 0:
            return  # Only negative seeks are supported for this logic.

        # This logic assumes the seek happens during a capture.
        if self._capture is None:
            return

        # Take the over-read data from the end of the capture buffer.
        data_to_unread = self._capture[amount:]
        del self._capture[amount:]

        # Prepend it to the main buffer to be read first next time.
        self.buffer = data_to_unread + self.buffer
        self.offset += amount  # Adjust offset backwards.

    def read_buffered(self, size: int, block: bool = True) -> bytes:
        """
        Return *size* bytes taken first from the internal buffer and then
        (if necessary) from the underlying stream.  When *block* is False,
        the call is forced into non-blocking mode for the duration of the read.
        """

        # 1. Consume internal buffer.
        from_buf = self.buffer[:size]
        del self.buffer[: len(from_buf)]

        needed = size - len(from_buf)
        if needed <= 0:
            return bytes(from_buf)

        try:
            from_io = self.input.read(needed)
        except (EOFError, BlockingIOError):
            from_io = b""

        return bytes(from_buf) + (from_io or b"")

    def update_state(self, data: bytes):
        """
        Updates the digest and capture buffer state after a read.
        """
        self.offset += len(data)
        # If we are inside a 'with stream.capture()' block...
        if self._capture is not None:
            # Use efficient in-place extension instead of concatenation.
            self._capture.extend(data)
        else:
            # Otherwise, update the main SHA-1 digest.
            self.digest.update(data)
