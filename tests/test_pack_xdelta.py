from legit.pack_delta import Delta
from legit.pack_xdelta import XDelta


#   0               16               32               48
#   +----------------+----------------+----------------+
#   |the quick brown |fox jumps over t|he slow lazy dog|
#   +----------------+----------------+----------------+


def assert_delta(source: str, target: str, expected):
    delta = XDelta.create_index(source)
    actual = delta.compress(target)
    assert actual == expected


def test_compresses_string():
    source = "the quick brown fox jumps over the slow lazy dog"
    target = "a swift auburn fox jumps over three dormant hounds"

    assert_delta(
        source,
        target,
        [
            Delta.Insert("a swift aubur"),
            Delta.Copy(14, 19),
            Delta.Insert("ree dormant hounds"),
        ],
    )


def test_compresses_incomplete_block():
    source = "the quick brown fox jumps over the slow lazy dog"
    target = "he quick brown fox jumps over trees"

    assert_delta(
        source,
        target,
        [
            Delta.Copy(1, 31),
            Delta.Insert("rees"),
        ],
    )


def test_compresses_at_source_start():
    source = "the quick brown fox jumps over the slow lazy dog"
    target = "the quick brown "

    assert_delta(
        source,
        target,
        [
            Delta.Copy(0, 16),
        ],
    )


def test_compresses_at_source_start_with_right_expansion():
    source = "the quick brown fox jumps over the slow lazy dog"
    target = "the quick brown fox hops"

    assert_delta(
        source,
        target,
        [
            Delta.Copy(0, 20),
            Delta.Insert("hops"),
        ],
    )


def test_compresses_at_source_start_with_left_offset():
    source = "the quick brown fox jumps over the slow lazy dog"
    target = "behold the quick brown foal"

    assert_delta(
        source,
        target,
        [
            Delta.Insert("behold "),
            Delta.Copy(0, 18),
            Delta.Insert("al"),
        ],
    )


def test_compresses_at_source_end():
    source = "the quick brown fox jumps over the slow lazy dog"
    target = "he slow lazy dog"

    assert_delta(
        source,
        target,
        [
            Delta.Copy(32, 16),
        ],
    )


def test_compresses_at_source_end_with_left_expansion():
    source = "the quick brown fox jumps over the slow lazy dog"
    target = "under the slow lazy dog"

    assert_delta(
        source,
        target,
        [
            Delta.Insert("und"),
            Delta.Copy(28, 20),
        ],
    )


def test_compresses_at_source_end_with_right_offset():
    source = "the quick brown fox jumps over the slow lazy dog"
    target = "under the slow lazy dog's legs"

    assert_delta(
        source,
        target,
        [
            Delta.Insert("und"),
            Delta.Copy(28, 20),
            Delta.Insert("'s legs"),
        ],
    )


def test_compresses_unindexed_bytes():
    source = "the quick brown fox"
    target = "see the quick brown fox"

    assert_delta(
        source,
        target,
        [
            Delta.Insert("see "),
            Delta.Copy(0, 19),
        ],
    )


def test_does_not_compress_unindexed_bytes():
    source = "the quick brown fox"
    target = "a quick brown fox"

    assert_delta(
        source,
        target,
        [
            Delta.Insert("a quick brown fox"),
        ],
    )

