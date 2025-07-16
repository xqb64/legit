from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Union, cast

from legit.diff import diff
from legit.myers import Line


@dataclass
class Clean:
    lines: List[str]

    def __str__(self) -> str:
        return "".join(self.lines)

    def to_string(self, *args: Optional[str]) -> str:
        return "".join(self.lines)


@dataclass
class Conflict:
    o_lines: List[str]
    a_lines: List[str]
    b_lines: List[str]

    def _separator(
        self, text: List[str], char: str, name: Optional[str] = None
    ) -> None:
        text.append(char * 7)
        if name:
            text.append(f" {name}")
        text.append("\n")

    def to_string(
        self, a_name: Optional[str] = None, b_name: Optional[str] = None
    ) -> str:
        text: list[str] = []
        self._separator(text, "<", a_name)
        text.extend(self.a_lines)
        self._separator(text, "=")
        text.extend(self.b_lines)
        self._separator(text, ">", b_name)
        return "".join(text)


@dataclass
class Result:
    chunks: List[Union[Clean, Conflict]]

    def is_clean(self) -> bool:
        return not any(isinstance(chunk, Conflict) for chunk in self.chunks)

    def to_string(
        self, a_name: Optional[str] = None, b_name: Optional[str] = None
    ) -> str:
        return "".join(chunk.to_string(a_name, b_name) for chunk in self.chunks)


class Diff3:
    def __init__(self, o: List[str], a: List[str], b: List[str]) -> None:
        self.o: list[str] = o
        self.a: list[str] = a
        self.b: list[str] = b
        self.chunks: List[Union[Clean, Conflict]] = []
        self.line_o: int = 0
        self.line_a: int = 0
        self.line_b: int = 0
        self.match_a: dict[int, int] = {}
        self.match_b: dict[int, int] = {}

    @staticmethod
    def merge(
        o: Union[str, List[str]], a: Union[str, List[str]], b: Union[str, List[str]]
    ) -> Result:
        o_lines = o.splitlines(True) if isinstance(o, str) else o
        a_lines = a.splitlines(True) if isinstance(a, str) else a
        b_lines = b.splitlines(True) if isinstance(b, str) else b

        return Diff3(o_lines, a_lines, b_lines)._merge()

    def _merge(self) -> Result:
        self._setup()
        self._generate_chunks()
        return Result(self.chunks)

    def _setup(self) -> None:
        self.chunks = []
        self.line_o = self.line_a = self.line_b = 0

        self.match_a = self._match_set(self.a)
        self.match_b = self._match_set(self.b)

    def _match_set(self, file_lines: List[str]) -> dict[int, int]:
        matches = {}
        for edit in diff(self.o, file_lines):
            if edit.ty == "eql":
                matches[cast(Line, edit.a_line).number] = cast(Line, edit.b_line).number
        return matches

    def _generate_chunks(self) -> None:
        while True:
            i = self._find_next_mismatch()

            if i == 1:
                o, a, b = self._find_next_match()

                if a is not None and b is not None:
                    self._emit_chunk(o, a, b)
                else:
                    self._emit_final_chunk()
                    return
            elif i is not None:
                self._emit_chunk(self.line_o + i, self.line_a + i, self.line_b + i)
            else:
                self._emit_final_chunk()
                return

    def _find_next_mismatch(self) -> Optional[int]:
        i = 1
        while (
            self._in_bounds(i)
            and self._is_match(self.match_a, self.line_a, i)
            and self._is_match(self.match_b, self.line_b, i)
        ):
            i += 1
        return i if self._in_bounds(i) else None

    def _in_bounds(self, i: int) -> bool:
        return (
            self.line_o + i <= len(self.o)
            or self.line_a + i <= len(self.a)
            or self.line_b + i <= len(self.b)
        )

    def _is_match(self, matches: dict[int, int], offset: int, i: int) -> bool:
        return matches.get(self.line_o + i) == offset + i

    def _find_next_match(self) -> tuple[int, Optional[int], Optional[int]]:
        o = self.line_o + 1
        while o <= len(self.o) and not (o in self.match_a and o in self.match_b):
            o += 1
        return o, self.match_a.get(o), self.match_b.get(o)

    def _emit_chunk(self, o: int, a: int, b: int) -> None:
        self._write_chunk(
            self.o[self.line_o : o - 1],
            self.a[self.line_a : a - 1],
            self.b[self.line_b : b - 1],
        )
        self.line_o, self.line_a, self.line_b = o - 1, a - 1, b - 1

    def _emit_final_chunk(self) -> None:
        self._write_chunk(
            self.o[self.line_o :], self.a[self.line_a :], self.b[self.line_b :]
        )

    def _write_chunk(
        self, o_lines: List[str], a_lines: List[str], b_lines: List[str]
    ) -> None:
        if a_lines == o_lines or a_lines == b_lines:
            self.chunks.append(Clean(b_lines))
        elif b_lines == o_lines:
            self.chunks.append(Clean(a_lines))
        else:
            self.chunks.append(Conflict(o_lines, a_lines, b_lines))
