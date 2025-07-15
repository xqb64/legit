from typing import Union

from legit.revision import Revision


def assert_parse(
    expression: str,
    tree: Union[
        "Revision.Ref", "Revision.Parent", "Revision.Ancestor", "Revision.Upstream"
    ],
) -> None:
    assert Revision.parse(expression) == tree


def test_it_parses_HEAD() -> None:
    assert_parse("HEAD", Revision.Ref("HEAD"))


def test_it_parses_at_as_HEAD() -> None:
    assert_parse("@", Revision.Ref("HEAD"))


def test_it_parses_branch_name() -> None:
    assert_parse("master", Revision.Ref("master"))


def test_it_parses_object_id() -> None:
    oid = "3803cb6dc4ab0a852c6762394397dc44405b5ae4"
    assert_parse(oid, Revision.Ref(oid))


def test_it_parses_parent_ref() -> None:
    assert_parse("HEAD^", Revision.Parent(Revision.Ref("HEAD"), 1))


def test_it_parses_parent_ref_with_number() -> None:
    assert_parse("@^2", Revision.Parent(Revision.Ref("HEAD"), 2))


def test_it_parses_chain_of_parent_refs() -> None:
    tree = Revision.Parent(
        Revision.Parent(Revision.Parent(Revision.Ref("master"), 1), 1), 1
    )
    assert_parse("master^^^", tree)


def test_it_parses_ancestor_ref() -> None:
    assert_parse("@~3", Revision.Ancestor(Revision.Ref("HEAD"), 3))


def test_it_parses_chain_of_parents_and_ancestors() -> None:
    expr = "@~2^^~3"
    inner = Revision.Ancestor(Revision.Ref("HEAD"), 2)
    after_parents = Revision.Parent(Revision.Parent(inner, 1), 1)
    tree = Revision.Ancestor(after_parents, 3)
    assert_parse(expr, tree)


def test_it_parses_upstream() -> None:
    assert_parse("master@{uPsTrEaM}", Revision.Upstream(Revision.Ref("master")))


def test_it_parses_short_hand_upstream() -> None:
    assert_parse("master@{u}", Revision.Upstream(Revision.Ref("master")))


def test_it_parses_upstream_with_no_branch() -> None:
    assert_parse("@{u}", Revision.Upstream(Revision.Ref("HEAD")))


def test_it_parses_upstream_with_ancestor_operators() -> None:
    tree = Revision.Ancestor(
        Revision.Parent(Revision.Upstream(Revision.Ref("master")), 1), 3
    )
    assert_parse("master@{u}^~3", tree)
