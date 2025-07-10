from __future__ import annotations

from legit.diff import diff

a = list("ABCABBA")
b = list("CBABAC")

edits = diff(a, b)
for edit in edits:
    print(edit)
