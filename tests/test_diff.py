import pytest

from legit.diff import diff_hunks


def hunks(a, b):
    return [
        [hunk.header(), [str(edit) for edit in hunk.edits]] for hunk in diff_hunks(a, b)
    ]


DOC = ["the", "quick", "brown", "fox", "jumps", "over", "the", "lazy", "dog"]


def test_it_detects_deletion_at_start():
    changed = ["quick", "brown", "fox", "jumps", "over", "the", "lazy", "dog"]
    expected = [["@@ -1,4 +1,3 @@", ["-the", " quick", " brown", " fox"]]]
    assert hunks(DOC, changed) == expected


def test_it_detects_insertion_at_start():
    changed = [
        "so",
        "the",
        "quick",
        "brown",
        "fox",
        "jumps",
        "over",
        "the",
        "lazy",
        "dog",
    ]
    expected = [["@@ -1,3 +1,4 @@", ["+so", " the", " quick", " brown"]]]
    assert hunks(DOC, changed) == expected


def test_it_detects_change_skipping_start_and_end():
    changed = [
        "the",
        "quick",
        "brown",
        "fox",
        "leaps",
        "right",
        "over",
        "the",
        "lazy",
        "dog",
    ]
    expected = [
        [
            "@@ -2,7 +2,8 @@",
            [
                " quick",
                " brown",
                " fox",
                "-jumps",
                "+leaps",
                "+right",
                " over",
                " the",
                " lazy",
            ],
        ]
    ]
    assert hunks(DOC, changed) == expected


def test_it_puts_nearby_changes_in_same_hunk():
    changed = ["the", "brown", "fox", "jumps", "over", "the", "lazy", "cat"]
    expected = [
        [
            "@@ -1,9 +1,8 @@",
            [
                " the",
                "-quick",
                " brown",
                " fox",
                " jumps",
                " over",
                " the",
                " lazy",
                "-dog",
                "+cat",
            ],
        ]
    ]
    assert hunks(DOC, changed) == expected


def test_it_puts_distant_changes_in_different_hunks():
    changed = ["a", "quick", "brown", "fox", "jumps", "over", "the", "lazy", "cat"]
    expected = [
        ["@@ -1,4 +1,4 @@", ["-the", "+a", " quick", " brown", " fox"]],
        ["@@ -6,4 +6,4 @@", [" over", " the", " lazy", "-dog", "+cat"]],
    ]
    assert hunks(DOC, changed) == expected
