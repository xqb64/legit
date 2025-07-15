from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Generator, List

SYMBOLS: dict[str, str] = {
    "eql": " ",
    "ins": "+",
    "del": "-",
}


@dataclass
class Line:
    number: int
    text: str


@dataclass
class Edit:
    ty: str
    a_line: Line | None = None
    b_line: Line | None = None

    def __str__(self) -> str:
        line = self.a_line or self.b_line
        assert line is not None
        return SYMBOLS[self.ty] + line.text

    @property
    def a_lines(self) -> list[Line | None]:
        return [self.a_line]


class Myers:
    def __init__(self, a: list[Line], b: list[Line]):
        self.a = a
        self.b = b

    @classmethod
    def diff(cls, a: list[Line], b: list[Line]) -> list[Edit]:
        return cls(a, b)._diff()

    def _diff(self) -> list[Edit]:
        edits: list[Edit] = []

        for prev_x, prev_y, x, y in self._backtrack():
            if x == prev_x:
                b_line = self.b[prev_y]
                edits.append(Edit("ins", None, b_line))
            elif y == prev_y:
                a_line = self.a[prev_x]
                edits.append(Edit("del", a_line, None))
            else:
                a_line = self.a[prev_x]
                b_line = self.b[prev_y]
                edits.append(Edit("eql", a_line, b_line))

        edits.reverse()
        return edits

    def _backtrack(self) -> Generator[tuple[int, int, int, int]]:
        trace = self._shortest_edit()
        x, y = len(self.a), len(self.b)

        for d in range(len(trace) - 1, -1, -1):
            v = trace[d]
            k = x - y

            if k == -d or (k != d and v.get(k - 1, 0) < v.get(k + 1, 0)):
                prev_k = k + 1
            else:
                prev_k = k - 1

            prev_x = v.get(prev_k, 0)
            prev_y = prev_x - prev_k

            while x > prev_x and y > prev_y:
                yield x - 1, y - 1, x, y
                x -= 1
                y -= 1

            if d > 0:
                yield prev_x, prev_y, x, y

            x, y = prev_x, prev_y

    def _shortest_edit(self) -> list[dict[int, int]]:
        n, m = len(self.a), len(self.b)
        max_d = n + m
        v: dict[int, int] = {1: 0}
        trace: list[dict[int, int]] = []

        for d in range(max_d + 1):
            trace.append(v.copy())

            for k in range(-d, d + 1, 2):
                if k == -d or (k != d and v.get(k - 1, 0) < v.get(k + 1, 0)):
                    x = v.get(k + 1, 0)
                else:
                    x = v.get(k - 1, 0) + 1

                y = x - k

                while x < n and y < m and self.a[x].text == self.b[y].text:
                    x += 1
                    y += 1

                v[k] = x

                if x >= n and y >= m:
                    return trace

        return trace
