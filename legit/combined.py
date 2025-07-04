from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Generator, Iterable

from legit.myers import Edit, Line 

SYMBOLS = {
    "del": "-",
    "ins": "+",
    "eql": " ",
}

class Combined:
    """
    A Python port of the Ruby Diff::Combined class. It combines multiple
    diffs into a single iterable sequence of rows.
    """

    @dataclass
    class Row:
        """Represents a single row in a combined diff."""
        edits: List[Optional[Edit]]

        @property
        def ty(self) -> str:
            """Determines the type of the row ('ins', 'del', or 'eql')."""
            types = [edit.ty for edit in self.edits if edit]
            return "ins" if "ins" in types else types[0]

        @property
        def a_lines(self) -> List[Optional[Line]]:
            """Returns the list of 'a' lines for this row."""
            return [e.a_line if e else None for e in self.edits]

        @property
        def b_line(self) -> Optional[Line]:
            """Returns the 'b' line from the first edit."""
            first_edit = next((e for e in self.edits if e), None)
            return first_edit.b_line if first_edit else None

        def __str__(self) -> str:
            """Returns the string representation of the row (e.g., '- text')."""
            symbols = "".join([
                SYMBOLS.get(edit.ty if edit is not None else None, " ")
                for edit in self.edits
            ])
            
            del_edit = next((edit for edit in self.edits if edit and edit.ty == "del"), None)

            if del_edit is not None:
                line = del_edit.a_line
            else:
                line = self.edits[0].b_line

            return ''.join(symbols) + line.text

    def __init__(self, diffs: List[List[Edit]]):
        self._diffs = diffs
        self._offsets: List[int] = []

    def __iter__(self) -> Generator[Combined.Row, None, None]:
        """
        Allows the class to be used in loops (e.g., for row in combined_diff:).
        This is the equivalent of the `each` method in Ruby's Enumerable.
        """
        self._offsets = [0] * len(self._diffs)

        while True:
            for i, diff in enumerate(self._diffs):
                yield from self._consume_deletions(diff, i)

            if self._is_complete():
                return

            edits = [diff[offset] for offset, diff in self._offset_diffs()]
            self._offsets = [offset + 1 for offset in self._offsets]

            yield self.Row(edits)

    def _is_complete(self) -> bool:
        """Checks if all diffs have been fully processed."""
        return all(offset == len(diff) for offset, diff in self._offset_diffs())

    def _offset_diffs(self) -> Iterable[tuple[int, List[Edit]]]:
        """Zips the current offsets with their respective diffs."""
        return zip(self._offsets, self._diffs)

    def _consume_deletions(self, diff: List[Edit], i: int) -> Generator[Combined.Row, None, None]:
        """
        Yields rows for any consecutive deletions starting at the current
        offset for a given diff.
        """
        while self._offsets[i] < len(diff) and diff[self._offsets[i]].ty == 'del':
            edits: List[Optional[Edit]] = [None] * len(self._diffs)
            edits[i] = diff[self._offsets[i]]
            self._offsets[i] += 1

            yield self.Row(edits)
