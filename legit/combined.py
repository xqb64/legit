from __future__ import annotations

from dataclasses import dataclass
from typing import Generator, Iterable, List, Optional, cast

from legit.hunk import EditLike
from legit.myers import Edit, Line

SYMBOLS: dict[str, str] = {
    "del": "-",
    "ins": "+",
    "eql": " ",
}


class Combined:
    @dataclass
    class Row:
        edits: List[Optional[Edit]]

        @property
        def ty(self) -> str:
            types = [edit.ty for edit in self.edits if edit]
            return "ins" if "ins" in types else types[0]

        @property
        def a_lines(self) -> List[Optional[Line]]:
            return [e.a_line if e else None for e in self.edits]

        @property
        def b_line(self) -> Optional[Line]:
            first_edit = next((e for e in self.edits if e), None)
            return first_edit.b_line if first_edit else None

        def __str__(self) -> str:
            symbols = "".join(
                [SYMBOLS[edit.ty] if edit is not None else " " for edit in self.edits]
            )

            del_edit = next(
                (edit for edit in self.edits if edit and edit.ty == "del"), None
            )

            if del_edit is not None:
                line = del_edit.a_line
            else:
                line = cast(Edit, self.edits[0]).b_line

            assert line is not None

            return "".join(symbols) + line.text

    def __init__(self, diffs: List[List[Edit]]):
        self._diffs = diffs
        self._offsets: List[int] = []

    def __iter__(self) -> Generator[EditLike, None, None]:
        self._offsets = [0] * len(self._diffs)

        while True:
            for i, diff in enumerate(self._diffs):
                yield from self._consume_deletions(diff, i)

            if self._is_complete():
                return

            edits = cast(
                List[Optional[Edit]],
                [diff[offset] for offset, diff in self._offset_diffs()],
            )
            self._offsets = [offset + 1 for offset in self._offsets]

            yield self.Row(edits)

    def _is_complete(self) -> bool:
        return all(offset == len(diff) for offset, diff in self._offset_diffs())

    def _offset_diffs(self) -> Iterable[tuple[int, List[Edit]]]:
        return zip(self._offsets, self._diffs)

    def _consume_deletions(
        self, diff: List[Edit], i: int
    ) -> Generator[Combined.Row, None, None]:
        while self._offsets[i] < len(diff) and diff[self._offsets[i]].ty == "del":
            edits: List[Optional[Edit]] = [None] * len(self._diffs)
            edits[i] = diff[self._offsets[i]]
            self._offsets[i] += 1

            yield self.Row(edits)
