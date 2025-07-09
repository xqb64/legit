import io
import os
import hashlib
from typing import Callable, Tuple, BinaryIO, Optional

from legit.pack import InvalidPack


class Stream:
    """
    Binary input wrapper that

    • maintains a running SHA-1 of all data *not* captured,
    • supports an in-memory read-ahead buffer,
    • lets callers “capture” a region of the stream,
    • offers blocking / non-blocking reads identical to the Ruby code.
    """

    def __init__(self, inp: BinaryIO, buffer: bytes = b"") -> None:
        self.input: BinaryIO = inp
        self.digest = hashlib.sha1()
        self.offset = 0                       # total bytes returned to callers
        self.buffer = bytearray(buffer)       # unread prefetched data
        self._capture: Optional[bytearray] = None

    # ------------------------------------------------------------------ #
    # high-level helpers
    # ------------------------------------------------------------------ #
    def unread(self, data: bytes) -> None:
        """
        Push bytes back onto the internal buffer so that the next read()
        will return them first.
        """
        # If we’re in a capture, adjust the capture buffer:
        if self._capture is not None:
            # Remove those bytes from the end of the capture
            del self._capture[-len(data):]
        # And always push them back into the front of the read buffer:
        self.buffer = bytearray(data) + self.buffer
        self.offset -= len(data)

    def capture(self, block: Callable[[], "T"]) -> Tuple["T", bytes]:
        """
        Execute *block* while recording every byte it consumes.
        Returns (block_result, captured_bytes).
        """
        self._capture = bytearray()
        try:
            result = block()
            return result, bytes(self._capture)
        finally:
            # captured bytes contribute to the overall pack checksum
            self.digest.update(self._capture)
            self._capture = None

    def verify_checksum(self) -> None:
        """
        Git packs end with a 20-byte SHA-1 checksum of everything
        *preceding* the checksum itself.  Compare that value with the
        running digest we have been updating.
        """
        checksum_from_stream = self._read_buffered(20, block=True)
        if checksum_from_stream != self.digest.digest():
            raise InvalidPack("Checksum does not match value read from pack")

    # ------------------------------------------------------------------ #
    # basic read primitives
    # ------------------------------------------------------------------ #

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

    # ------------------------------------------------------------------ #
    # seeking  (only the “un-read” form used by pack-parser backtracking)
    # ------------------------------------------------------------------ #
    def seek(self, amount: int, whence: int = os.SEEK_SET) -> None:
        if amount >= 0 or whence != os.SEEK_SET or self._capture is None:
            return
    
        # amount is negative, so we want to "unread" abs(amount) bytes
        bytes_to_unread = abs(amount)
        
        if bytes_to_unread > len(self._capture):
            raise ValueError(f"Cannot seek back {bytes_to_unread} bytes, only {len(self._capture)} available")
        
        # Take the last N bytes from capture and put them back in buffer
        unread_data = self._capture[-bytes_to_unread:]
        del self._capture[-bytes_to_unread:]
        
        self.buffer = bytearray(unread_data) + self.buffer
        self.offset += amount  # amount is negative, so this decreases offset

   #  def seek(self, amount: int, whence: int = os.SEEK_SET) -> None:
   #      """
   #      Negative SEEK_SET is the only form used by the Ruby code.
   #      We support it only while a capture is active.
   #      """
   #      if amount >= 0 or whence != os.SEEK_SET or self._capture is None:
   #          return

   #      # move data *back* from capture to the read-ahead buffer
   #      unread = self._capture[amount:]
   #      del self._capture[amount:]
   #      self.buffer = bytearray(unread) + self.buffer
   #      self.offset += amount  # amount is negative

    # ------------------------------------------------------------------ #
    # private helpers
    # ------------------------------------------------------------------ #
    
    def _read_buffered(self, size: int, block: bool = True) -> bytes:
        # 1. Pull from our own buffer first
        from_buf = bytes(self.buffer[:size])
        # remove what we took
        del self.buffer[:len(from_buf)]

        # 2. How many more bytes we still need
        needed = size - len(from_buf)
        if needed <= 0:
            return from_buf

        try:
            chunk = self.input.read(needed)
            chunk = chunk or b''
            return from_buf + chunk

        except (EOFError, BlockingIOError):
            # On EOF or EWOULDBLOCK, just return whatever we had
            return from_buf
   
    def __read_buffered(self, size: int, *, block: bool) -> bytes:
        """
        Return up to *size* bytes, preferring the internal buffer.
        If fewer than *size* bytes are immediately available, we:
          • in blocking mode  – read as much as the OS will give us,
          • in non-blocking   – read whatever is currently ready.
        This matches the behaviour of the Ruby version.
        """
        # 1. consume from in-memory buffer
        from_buf = self.buffer[:size]
        del self.buffer[:len(from_buf)]

        needed = size - len(from_buf)
        if needed <= 0:
            return bytes(from_buf)

        # 2. read the remainder from the underlying file-like object
        read_data = b""
        fd: Optional[int] = None

        if not block:
            try:
                fd = self.input.fileno()
            except (AttributeError, io.UnsupportedOperation):
                fd = None

            prev_flag = os.get_blocking(fd)
            if prev_flag:                       # temporarily non-blocking
                os.set_blocking(fd, False)

        try:
            read_data = self.input.read(needed) or b""
        except (BlockingIOError, EOFError):
            read_data = b""
        finally:
            if fd is not None:
                os.set_blocking(fd, prev_flag)  # restore original flag

        return bytes(from_buf) + read_data

    def _update_state(self, data: bytes) -> None:
        self.offset += len(data)
        if self._capture is not None:
            self._capture.extend(data)
        else:
            self.digest.update(data)

    # ------------------------------------------------------------------ #
    # convenience
    # ------------------------------------------------------------------ #

    @property
    def eof(self) -> bool:
        """
        There is still unread data if either the internal buffer
        is non-empty or the underlying stream has more bytes.
        """
        if self.buffer:
            return False

        # Try to peek 1 byte; if we get something push it back
        b = self.input.read(1)
        if not b:
            return True
        self.buffer.extend(b)
        return False



# import os
# import hashlib
# from legit.pack import InvalidPack
# 
# 
# class Stream:
#     def __init__(self, f, buffer=b""):
#         self.input = f
#         self.digest = hashlib.sha1()
#         self.offset = 0
#         self.buffer = bytearray(buffer)
#         self._capture = None
# 
#     @property
#     def eof(self) -> bool:
#         if self.buffer:
#             return False
#         
#         data = self.input.read(1)
#         if not data:
#             return True  # End of stream
#         
#         self.buffer.extend(data)
#         return False
# 
#     def capture(self, block):
#         self._capture = bytearray()
#         block_result = block()
#         result = (block_result, bytes(self._capture))
#         self.digest.update(self._capture)
#         self._capture = None
#         return result
# 
#     def verify_checksum(self):
#         expected = self.digest.digest()
#         actual = self.read(20)
#         if actual != expected:
#             raise InvalidPack("Checksum does not match value read from pack")
# 
#     def read(self, size: int) -> bytes:
#         data = self.read_buffered(size, block=True)
#         self.update_state(data)
#         return data
# 
#     def read_nonblock(self, size: int) -> bytes:
#         data = self.read_buffered(size, block=False)
#         self.update_state(data)
#         return data
# 
#     def readbyte(self) -> int:
#         """
#         Reads a single byte and returns it as an integer.
# 
#         Raises:
#             EOFError: If the end of the stream is reached unexpectedly.
#         """
#         b = self.read(1)
#         if not b:
#             raise EOFError("Unexpected EOF when reading a byte")
#         return b[0]
# 
#     def seek(self, amount: int):
#         """
#         Custom seek for buffer manipulation. A negative amount 'un-reads' data
#         by moving it from the capture buffer back to the main read buffer.
#         """
#         if amount >= 0:
#             return  # Only negative seeks are supported for this logic.
# 
#         # This logic assumes the seek happens during a capture.
#         if self._capture is None:
#             return
# 
#         # Take the over-read data from the end of the capture buffer.
#         data_to_unread = self._capture[amount:]
#         del self._capture[amount:]
# 
#         # Prepend it to the main buffer to be read first next time.
#         self.buffer = data_to_unread + self.buffer
#         self.offset += amount  # Adjust offset backwards.
# 
#     def read_buffered(self, size: int, block: bool = True) -> bytes:
#         """
#         Return *size* bytes taken first from the internal buffer and then
#         (if necessary) from the underlying stream.  When *block* is False,
#         the call is forced into non-blocking mode for the duration of the read.
#         """
# 
#         # 1. Consume internal buffer.
#         from_buf = self.buffer[:size]
#         del self.buffer[: len(from_buf)]
# 
#         needed = size - len(from_buf)
#         if needed <= 0:
#             return bytes(from_buf)
# 
#         fd = self.input.fileno()
#         if not block:
#             was_blocking = os.get_blocking(fd)
#             os.set_blocking(fd, False)
# 
#         try:
#             from_io = self.input.read(needed)
#         except (EOFError, BlockingIOError):
#             from_io = b""
#         finally:
#             if not block:
#                 os.set_blocking(fd, was_blocking)
# 
#         return bytes(from_buf) + (from_io or b"")
# 
#     def update_state(self, data: bytes):
#         self.offset += len(data)
#         if self._capture is not None:
#             self._capture.extend(data)
#         else:
#             self.digest.update(data)
