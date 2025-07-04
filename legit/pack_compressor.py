from typing import Any, Optional, List
from legit.pack_window import Window
from legit.pack_delta import Delta


class Compressor:
    """
    Finds and creates delta objects to reduce packfile size.
    """

    # Constants
    OBJECT_SIZE_MIN = 50
    OBJECT_SIZE_MAX = 0x20000000
    MAX_DEPTH = 50
    WINDOW_SIZE = 8

    def __init__(self, database: Any, progress: Optional[Any]):
        """
        Initializes the Compressor.

        Args:
            database: A database object to load raw object data.
            progress: An optional progress indicator object.
        """
        self._database = database
        self._window = Window(self.WINDOW_SIZE)
        self._progress = progress
        self._objects: List[Any] = []

    def max_size_heuristic(self, source, target):
        if target.delta:
            max_size = target.delta.size
            ref_depth = target.depth
        else:
            max_size = target.size / 2 - 20
            ref_depth = 1

        return (
            max_size
            * (Compressor.MAX_DEPTH - source.depth)
            / (Compressor.MAX_DEPTH + 1 - ref_depth)
        )

    def add(self, entry: Any) -> None:
        """
        Adds an entry to the list of objects to be compressed.

        The entry is ignored if its size is outside the defined range.

        Args:
            entry: The object entry to add.
        """
        if not (self.OBJECT_SIZE_MIN <= entry.size <= self.OBJECT_SIZE_MAX):
            return
        self._objects.append(entry)

    def build_deltas(self) -> None:
        """
        Builds deltas for the added objects to compress them.
        """
        if self._progress:
            self._progress.start("Compressing objects", len(self._objects))

        # Sort objects in descending order based on their sort_key.
        # Python's sort is ascending, so we use reverse=True.
        self._objects.sort(key=lambda e: e.sort_key(), reverse=True)

        for entry in self._objects:
            self._build_delta(entry)
            if self._progress:
                self._progress.tick()

        if self._progress:
            self._progress.stop()

    def _build_delta(self, entry: Any) -> None:
        """
        (Private) Tries to find a suitable delta base for a given entry.
        """
        obj = self._database.load_raw(entry.oid)
        target = self._window.add(entry, obj.data)

        # The window allows us to check against recent objects
        for source in self._window:
            self._try_delta(source, target)

    def _try_delta(self, source: Any, target: Any) -> None:
        """
        (Private) Attempts to create a delta between a source and a target.

        If the new delta is more efficient, it's assigned to the target's entry.
        """
        if source.type != target.type:
            return
        if source.depth >= self.MAX_DEPTH:
            return

        max_size = self.max_size_heuristic(source, target)
        if not self.compatible_sizes(source, target, max_size):
            return

        delta = Delta(source, target)
        size = target.entry.packed_size

        # Don't use a delta that is larger than the current packed object
        if delta.size > max_size:
            return
        # For deltas of the same size, only use it if it reduces the delta chain depth
        if delta.size == size and (delta.base.depth + 1) >= target.entry.depth:
            return

        target.entry.assign_delta(delta)

    def compatible_sizes(self, source, target, max_size):
        size_diff = max([target.size - source.size, 0])
        if max_size == 0:
            return False
        if size_diff >= max_size:
            return False
        if target.size < source.size / 32:
            return False
        return True
