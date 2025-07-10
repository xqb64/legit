from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, cast

from legit.db_loose import Raw
from legit.pack_delta import Delta
from legit.pack_entry import Entry
from legit.pack_window import Window

if TYPE_CHECKING:
    from legit.database import Database
    from legit.progress import Progress


class Compressor:
    OBJECT_SIZE_MIN: int = 50
    OBJECT_SIZE_MAX: int = 0x20000000
    MAX_DEPTH: int = 50
    WINDOW_SIZE: int = 8

    def __init__(self, database: Database, progress: Optional[Progress]):
        self._database = database
        self._window = Window(self.WINDOW_SIZE)
        self._progress = progress
        self._objects: List[Entry] = []

    def max_size_heuristic(
        self, source: Window.Unpacked, target: Window.Unpacked
    ) -> float:
        if target.delta:
            max_size = target.delta.size
            ref_depth = target.depth
        else:
            max_size = target.size // 2 - 20
            ref_depth = 1

        return (
            max_size
            * (Compressor.MAX_DEPTH - source.depth)
            / (Compressor.MAX_DEPTH + 1 - ref_depth)
        )

    def add(self, entry: Entry) -> None:
        if not (self.OBJECT_SIZE_MIN <= entry.size <= self.OBJECT_SIZE_MAX):
            return
        self._objects.append(entry)

    def build_deltas(self) -> None:
        if self._progress:
            self._progress.start("Compressing objects", len(self._objects))

        self._objects.sort(key=lambda e: e.sort_key(), reverse=True)

        for entry in self._objects:
            self._build_delta(entry)
            if self._progress:
                self._progress.tick()

        if self._progress:
            self._progress.stop()

    def _build_delta(self, entry: Entry) -> None:
        obj = self._database.load_raw(entry.oid)
        target = self._window.add(entry, cast(bytes, cast(Raw, obj).data))

        for source in self._window:
            self._try_delta(source, target)

    def _try_delta(self, source: Window.Unpacked, target: Window.Unpacked) -> None:
        if source.type != target.type:
            return
        if source.depth >= self.MAX_DEPTH:
            return

        max_size = self.max_size_heuristic(source, target)
        if not self.compatible_sizes(source, target, max_size):
            return

        delta = Delta(source, target)
        size = target.entry.packed_size

        if delta.size > max_size:
            return
        if delta.size == size and (delta.base.depth + 1) >= target.entry.depth:
            return

        target.entry.assign_delta(delta)

    def compatible_sizes(
        self, source: Window.Unpacked, target: Window.Unpacked, max_size: float
    ) -> bool:
        size_diff = max([target.size - source.size, 0])
        if max_size == 0:
            return False
        if size_diff >= max_size:
            return False
        if target.size < source.size / 32:
            return False
        return True
