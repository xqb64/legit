from typing import Union
import pytest

from legit.revision import Revision


def assert_parse(expression: str, tree: Union['Revision.Ref', 'Revision.Parent', 'Revision.Ancestor']):
    """
    Helper to assert that parsing the given expression yields the expected tree.
    """
    assert Revision.parse(expression) == tree


def test_parses_HEAD():
    assert_parse("HEAD", Revision.Ref("HEAD"))


def test_parses_at_as_HEAD():
    assert_parse("@", Revision.Ref("HEAD"))


def test_parses_branch_name():
    assert_parse("master", Revision.Ref("master"))


def test_parses_object_id():
    oid = "3803cb6dc4ab0a852c6762394397dc44405b5ae4"
    assert_parse(oid, Revision.Ref(oid))


def test_parses_parent_ref():
    # HEAD^   -> parent number 1
    assert_parse("HEAD^", Revision.Parent(Revision.Ref("HEAD"), 1))


def test_parses_parent_ref_with_number():
    # @^2     -> parent number 2
    assert_parse("@^2", Revision.Parent(Revision.Ref("HEAD"), 2))


def test_parses_chain_of_parent_refs():
    # master^^^ -> master^1^1^1
    tree = Revision.Parent(
        Revision.Parent(
            Revision.Parent(Revision.Ref("master"), 1), 1
        ), 1
    )
    assert_parse("master^^^", tree)


def test_parses_ancestor_ref():
    assert_parse("@~3", Revision.Ancestor(Revision.Ref("HEAD"), 3))


def test_parses_chain_of_parents_and_ancestors():
    expr = "@~2^^~3"
    # Equivalent to: ((HEAD~2)^^)~3
    inner = Revision.Ancestor(Revision.Ref("HEAD"), 2)
    after_parents = Revision.Parent(Revision.Parent(inner, 1), 1)
    tree = Revision.Ancestor(after_parents, 3)
    assert_parse(expr, tree)

