from typing import Any, Iterator, Optional, List


class Window:
    class Unpacked:
        def __init__(self, entry: Any, data: bytes):
            self.entry = entry
            self.data = data
            self.delta_index: Optional[int] = None

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
        if size <= 0:
            raise ValueError("Window size must be positive.")
        self._objects: List[Optional[Window.Unpacked]] = [None] * size
        self._offset: int = 0

    def add(self, entry: Any, data: bytes) -> "Window.Unpacked":
        unpacked = self.Unpacked(entry, data)
        self._objects[self._offset] = unpacked
        self._offset = (self._offset + 1) % len(self._objects)
        return unpacked

    def __iter__(self) -> Iterator[Unpacked]:
        size = len(self._objects)
        limit = (self._offset - 1 + size) % size
        cursor = (self._offset - 2 + size) % size

        for _ in range(size - 1):
            if cursor == limit:
                break

            unpacked = self._objects[cursor]
            if unpacked:
                yield unpacked

            cursor = (cursor - 1 + size) % size
