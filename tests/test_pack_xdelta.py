from legit.pack_delta import Delta
from legit.pack_xdelta import XDelta

#   0               16               32               48
#   +----------------+----------------+----------------+
#   |the quick brown |fox jumps over t|he slow lazy dog|
#   +----------------+----------------+----------------+


def assert_delta(
    source: bytes, target: bytes, expected: list[Delta.Copy | Delta.Insert]
) -> None:
    delta = XDelta.create_index(source)
    actual = delta.compress(target)
    assert actual == expected


def test_compresses_string() -> None:
    source = b"the quick brown fox jumps over the slow lazy dog"
    target = b"a swift auburn fox jumps over three dormant hounds"

    assert_delta(
        source,
        target,
        [
            Delta.Insert(b"a swift aubur"),
            Delta.Copy(14, 19),
            Delta.Insert(b"ree dormant hounds"),
        ],
    )


def test_compresses_incomplete_block() -> None:
    source = b"the quick brown fox jumps over the slow lazy dog"
    target = b"he quick brown fox jumps over trees"

    assert_delta(
        source,
        target,
        [
            Delta.Copy(1, 31),
            Delta.Insert(b"rees"),
        ],
    )


def test_compresses_at_source_start() -> None:
    source = b"the quick brown fox jumps over the slow lazy dog"
    target = b"the quick brown "

    assert_delta(
        source,
        target,
        [
            Delta.Copy(0, 16),
        ],
    )


def test_compresses_at_source_start_with_right_expansion() -> None:
    source = b"the quick brown fox jumps over the slow lazy dog"
    target = b"the quick brown fox hops"

    assert_delta(
        source,
        target,
        [
            Delta.Copy(0, 20),
            Delta.Insert(b"hops"),
        ],
    )


def test_compresses_at_source_start_with_left_offset() -> None:
    source = b"the quick brown fox jumps over the slow lazy dog"
    target = b"behold the quick brown foal"

    assert_delta(
        source,
        target,
        [
            Delta.Insert(b"behold "),
            Delta.Copy(0, 18),
            Delta.Insert(b"al"),
        ],
    )


def test_compresses_at_source_end() -> None:
    source = b"the quick brown fox jumps over the slow lazy dog"
    target = b"he slow lazy dog"

    assert_delta(
        source,
        target,
        [
            Delta.Copy(32, 16),
        ],
    )


def test_compresses_at_source_end_with_left_expansion() -> None:
    source = b"the quick brown fox jumps over the slow lazy dog"
    target = b"under the slow lazy dog"

    assert_delta(
        source,
        target,
        [
            Delta.Insert(b"und"),
            Delta.Copy(28, 20),
        ],
    )


def test_compresses_at_source_end_with_right_offset() -> None:
    source = b"the quick brown fox jumps over the slow lazy dog"
    target = b"under the slow lazy dog's legs"

    assert_delta(
        source,
        target,
        [
            Delta.Insert(b"und"),
            Delta.Copy(28, 20),
            Delta.Insert(b"'s legs"),
        ],
    )


def test_compresses_unindexed_bytes() -> None:
    source = b"the quick brown fox"
    target = b"see the quick brown fox"

    assert_delta(
        source,
        target,
        [
            Delta.Insert(b"see "),
            Delta.Copy(0, 19),
        ],
    )


def test_does_not_compress_unindexed_bytes() -> None:
    source = b"the quick brown fox"
    target = b"a quick brown fox"

    assert_delta(
        source,
        target,
        [
            Delta.Insert(b"a quick brown fox"),
        ],
    )
