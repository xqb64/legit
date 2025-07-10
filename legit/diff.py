from __future__ import annotations

from typing import List, Sequence, Union

from legit.combined import Combined
from legit.hunk import EditLike, Hunk
from legit.myers import Edit, Line, Myers


def lines(document: Union[str, List[str]]) -> List[Line]:
    if isinstance(document, str):
        doc_lines = document.splitlines()
    else:
        doc_lines = document
    return [Line(i + 1, text) for i, text in enumerate(doc_lines)]


def diff(a: Union[str, List[str]], b: Union[str, List[str]]) -> List[Edit]:
    return Myers.diff(lines(a), lines(b))


def diff_hunks(a: Union[str, List[str]], b: Union[str, List[str]]) -> List[Hunk]:
    return Hunk.filter(diff(a, b))


def diff_combined(
    a_versions: Sequence[Union[str, List[str]]], b_version: Union[str, List[str]]
) -> Sequence[EditLike]:
    diffs = [diff(a, b_version) for a in a_versions]
    combined_rows = list(Combined(diffs))
    return combined_rows


def combined_hunks(
    a_versions: Sequence[Union[str, List[str]]], b_version: Union[str, List[str]]
) -> List[Hunk]:
    return Hunk.filter(diff_combined(a_versions, b_version))
