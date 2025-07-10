from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Protocol, Sequence, cast, runtime_checkable

from legit.myers import Line

HUNK_CONTEXT = 3


@runtime_checkable
class EditLike(Protocol):
    @property
    def ty(self) -> str: ...
    @property
    def a_lines(self) -> list[Line | None]: ...
    @property
    def b_line(self) -> Line | None: ...


@dataclass
class Hunk:
    a_starts: List[int]
    b_start: Optional[int]
    edits: List[EditLike] = field(default_factory=list)

    @staticmethod
    def filter(edits: Sequence[EditLike]) -> List[Hunk]:
        hunks: List[Hunk] = []
        offset = 0

        while True:
            while offset < len(edits) and edits[offset].ty == "eql":
                offset += 1

            if offset >= len(edits):
                return hunks

            offset -= HUNK_CONTEXT + 1

            a_starts = (
                []
                if offset < 0
                else [line.number for line in edits[offset].a_lines if line is not None]
            )

            b_start = None if offset < 0 else cast(Line, edits[offset].b_line).number

            hunk = Hunk(a_starts=a_starts, b_start=b_start, edits=[])
            hunks.append(hunk)

            offset = Hunk._build(hunks[-1], edits, offset)

    @staticmethod
    def _build(hunk: Hunk, edits: Sequence[EditLike], offset: int) -> int:
        counter = -1

        while counter != 0:
            if offset >= 0 and counter > 0:
                hunk.edits.append(edits[offset])

            offset += 1
            if offset >= len(edits):
                break

            try:
                spam = edits[offset + HUNK_CONTEXT]
            except IndexError:
                spam = None

            if spam is not None and (spam.ty == "ins" or spam.ty == "del"):
                counter = 2 * HUNK_CONTEXT + 1
            else:
                counter -= 1

        return offset

    def header(self) -> str:
        list_of_a_lines = [e.a_lines for e in self.edits]
        transposed_a_lines = list(zip(*list_of_a_lines))

        offsets = []
        for i, lines in enumerate(transposed_a_lines):
            try:
                a_start = self.a_starts[i]
            except IndexError:
                a_start = None
            fmt = self._format("-", lines, a_start)
            offsets.append(fmt)

        b_lines = [e.b_line for e in self.edits]
        offsets.append(self._format("+", b_lines, self.b_start))

        sep = "@" * len(offsets)

        return " ".join([sep, *offsets, sep])

    def _format(
        self, sign: str, lines: Sequence[Optional[Line]], start: Optional[int]
    ) -> str:
        lines = [ln for ln in lines if ln is not None]

        start_val = cast(Line, lines[0]).number if lines else start

        if start_val is None:
            start_val = 0

        return f"{sign}{start_val},{len(lines)}"
