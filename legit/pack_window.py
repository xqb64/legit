from typing import Any, Iterator, Optional, List


class Window:
    """
    A sliding window of recently seen objects, used for delta compression.
    It functions as a fixed-size circular buffer.
    """

    class Unpacked:
        """
        A container for an Entry and its decompressed data.
        In Python, we can use a simple class or a dataclass.
        """
        def __init__(self, entry: Any, data: bytes):
            self.entry = entry
            self.data = data
            self.delta_index: Optional[int] = None

        # Delegate properties to the wrapped entry object
        @property
        def type(self) -> str:
            return self.entry.ty

        @property
        def size(self) -> int:
            return self.entry.size

        @property
        def delta(self) -> Optional[Any]:
            return self.entry.delta

        @property
        def depth(self) -> int:
            return self.entry.depth

    def __init__(self, size: int):
        """
        Initializes the Window with a fixed size.

        Args:
            size: The number of objects to keep in the window.
        """
        if size <= 0:
            raise ValueError("Window size must be positive.")
        # Initialize a list with None placeholders
        self._objects: List[Optional[Window.Unpacked]] = [None] * size
        self._offset: int = 0

    def add(self, entry: Any, data: bytes) -> 'Window.Unpacked':
        """
        Adds a new object to the window, replacing the oldest if full.

        Args:
            entry: The metadata entry for the object.
            data: The raw, decompressed data of the object.

        Returns:
            The Unpacked object that was added to the window.
        """
        unpacked = self.Unpacked(entry, data)
        self._objects[self._offset] = unpacked
        # Move the offset to the next slot, wrapping around if necessary
        self._offset = (self._offset + 1) % len(self._objects)
        return unpacked

    def __iter__(self) -> Iterator[Unpacked]:
        """
        Provides an iterator that yields objects in the window.

        It iterates backward from the most recently added item,
        skipping the very last one added (as it cannot be a delta base
        for itself). This mimics the Ruby `each` method's logic.
        """
        size = len(self._objects)
        # The last item added is at `wrap(self._offset - 1)`.
        # The loop starts from the item before that.
        limit = (self._offset - 1 + size) % size
        cursor = (self._offset - 2 + size) % size

        # We iterate for at most `size - 1` items
        for _ in range(size - 1):
            if cursor == limit:
                break

            unpacked = self._objects[cursor]
            if unpacked:
                yield unpacked

            # Move cursor backward, wrapping around
            cursor = (cursor - 1 + size) % size
