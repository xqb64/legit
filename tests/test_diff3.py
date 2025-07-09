import textwrap
from legit.diff3 import Diff3


def test_it_cleanly_merges_two_lists():
    merge = Diff3.merge(["a", "b", "c"], ["d", "b", "c"], ["a", "b", "e"])
    assert merge.is_clean()
    assert merge.to_string() == "dbe"


def test_it_cleanly_merges_two_lists_with_same_edit():
    merge = Diff3.merge(["a", "b", "c"], ["d", "b", "c"], ["d", "b", "e"])
    assert merge.is_clean()
    assert merge.to_string() == "dbe"


def test_it_uncleanly_merges_two_lists():
    merge = Diff3.merge(["a", "b", "c"], ["d", "b", "c"], ["e", "b", "c"])
    assert not merge.is_clean()

    expected = textwrap.dedent(
        """\
        <<<<<<<
        d=======
        e>>>>>>>
        bc"""
    )
    assert merge.to_string() == expected


def test_it_uncleanly_merges_two_lists_against_an_empty_list():
    merge = Diff3.merge([], ["d", "b", "c"], ["e", "b", "c"])
    assert not merge.is_clean()

    expected = textwrap.dedent(
        """\
        <<<<<<<
        dbc=======
        ebc>>>>>>>
        """
    )
    assert merge.to_string() == expected


def test_it_uncleanly_merges_two_lists_with_head_names():
    merge = Diff3.merge(["a", "b", "c"], ["d", "b", "c"], ["e", "b", "c"])
    assert not merge.is_clean()

    expected = textwrap.dedent(
        """\
        <<<<<<< left
        d=======
        e>>>>>>> right
        bc"""
    )
    assert merge.to_string("left", "right") == expected
