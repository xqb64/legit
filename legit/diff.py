from typing import Union, List
from legit.myers import Edit, Line, Myers
from legit.hunk import Hunk
from legit.combined import Combined


def lines(document: Union[str, List[str]]) -> List[Line]:
    """
    Turn a string or list of strings into a list of Line objects,
    numbering from 1.
    """
    if isinstance(document, str):
        doc_lines = document.splitlines()
    else:
        doc_lines = document
    return [Line(i + 1, text) for i, text in enumerate(doc_lines)]


def diff(a: Union[str, List[str]], b: Union[str, List[str]]) -> List[Edit]:
    """
    Compute the diff between a and b, returning a list of Edit objects.
    """
    return Myers.diff(lines(a), lines(b))


def diff_hunks(a: Union[str, List[str]], b: Union[str, List[str]]) -> List[Hunk]:
    return Hunk.filter(diff(a, b))


def diff_combined(a_versions, b_version) -> List[Combined.Row]:
    diffs: List[List[Edit]] = [diff(a, b_version) for a in a_versions]
    combined_rows = list(Combined(diffs))
    return combined_rows


def combined_hunks(a_versions, b_version) -> List[Hunk]:
    return Hunk.filter(diff_combined(a_versions, b_version))
