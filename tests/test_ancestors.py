import datetime
from pathlib import Path
from typing import Callable, TypeAlias, cast

import pytest

from legit.author import Author
from legit.bases import Bases
from legit.commit import Commit
from legit.common_ancestors import CommonAncestors
from legit.database import Database

Ancestor: TypeAlias = Callable[[str, str], str | list[str]]
MergeBase: TypeAlias = Callable[[str, str], str | list[str]]


class GraphBuilder:
    def __init__(self, db: Database) -> None:
        self.db: Database = db
        self.commits: dict[str, str] = {}

    def commit(self, parents: list[str], message: str) -> None:
        parent_oids: list[str] = [self.commits[p] for p in parents]
        author: Author = Author(
            "A. U. Thor", "author@example.com", datetime.datetime.now().astimezone()
        )
        commit: Commit = Commit(parent_oids, "0" * 40, author, author, message)
        self.db.store(commit)
        self.commits[message] = commit.oid

    def chain(self, names: list[str | None]) -> None:
        for parent, msg in zip(names, names[1:]):
            parents = [] if parent is None else [parent]
            assert msg is not None
            self.commit(parents, msg)


@pytest.fixture
def db(repo_path: Path) -> Database:
    return Database(repo_path / "objects")


@pytest.fixture
def builder(db: Database) -> GraphBuilder:
    return GraphBuilder(db)


@pytest.fixture
def ancestor(builder: GraphBuilder, db: Database) -> Ancestor:
    def _ancestor(left: str, right: str) -> str | list[str]:
        common = CommonAncestors(db, builder.commits[left], [builder.commits[right]])
        msgs = [cast(Commit, db.load(oid)).message for oid in common.find()]
        return msgs[0] if len(msgs) == 1 else sorted(msgs)

    return _ancestor


@pytest.fixture
def merge_base(builder: GraphBuilder, db: Database) -> MergeBase:
    def _merge_base(left: str, right: str) -> str | list[str]:
        bases = Bases(db, builder.commits[left], builder.commits[right])
        msgs = [cast(Commit, db.load(oid)).message for oid in bases.find()]
        return msgs[0] if len(msgs) == 1 else sorted(msgs)

    return _merge_base


class TestLinearHistory:
    #   o---o---o---o
    #   A   B   C   D

    @pytest.fixture(autouse=True)
    def setup_chain(self, builder: GraphBuilder) -> None:
        builder.chain([None, "A", "B", "C", "D"])

    def test_it_finds_the_common_ancestor_of_a_commit_with_itself(
        self, ancestor: Ancestor
    ) -> None:
        assert ancestor("D", "D") == "D"

    def test_it_finds_the_commit_that_is_an_ancestor_of_other(
        self, ancestor: Ancestor
    ) -> None:
        assert ancestor("B", "D") == "B"

    def test_it_finds_the_same_commit_if_the_args_are_reversed(
        self, ancestor: Ancestor
    ) -> None:
        assert ancestor("D", "B") == "B"

    def test_it_finds_a_root_commit(self, ancestor: Ancestor) -> None:
        assert ancestor("A", "C") == "A"

    def test_it_finds_the_intersection_of_the_root_commit_with_itself(
        self, ancestor: Ancestor
    ) -> None:
        assert ancestor("A", "A") == "A"


class TestForkingHistory:
    #          E   F   G   H
    #          o---o---o---o
    #         /         \
    #        /  C   D    \
    #   o---o---o---o     o---o
    #   A   B    \        J   K
    #             \
    #              o---o---o
    #              L   M   N

    @pytest.fixture(autouse=True)
    def setup_chain(self, builder: GraphBuilder) -> None:
        b = builder
        b.chain([None, "A", "B", "C", "D"])
        b.chain(["B", "E", "F", "G", "H"])
        b.chain(["G", "J", "K"])
        b.chain(["C", "L", "M", "N"])

    def test_it_finds_the_nearest_fork_point(self, ancestor: Ancestor) -> None:
        assert ancestor("H", "K") == "G"

    def test_it_finds_an_ancestor_multiple_forks_away(self, ancestor: Ancestor) -> None:
        assert ancestor("D", "K") == "B"

    def test_it_finds_the_same_fork_point_for_any_point_on_a_branch(
        self, ancestor: Ancestor
    ) -> None:
        assert ancestor("D", "L") == "C"
        assert ancestor("M", "D") == "C"
        assert ancestor("D", "N") == "C"

    def test_it_finds_the_commit_that_is_an_ancestor_of_other(
        self, ancestor: Ancestor
    ) -> None:
        assert ancestor("K", "E") == "E"

    def test_it_finds_the_root_commit(self, ancestor: Ancestor) -> None:
        assert ancestor("J", "A") == "A"


class TestWithMerge:
    #   A   B   C   G   H
    #   o---o---o---o---o
    #        \     /
    #         o---o---o
    #         D   E   F

    @pytest.fixture(autouse=True)
    def setup_chain(self, builder: GraphBuilder) -> None:
        b = builder
        b.chain([None, "A", "B", "C"])
        b.chain(["B", "D", "E", "F"])
        b.commit(["C", "E"], "G")
        b.chain(["G", "H"])

    def test_it_finds_the_most_recent_common_ancestor(self, ancestor: Ancestor) -> None:
        assert ancestor("H", "F") == "E"

    def test_it_finds_the_common_ancestor_of_a_merge_and_its_parents(
        self, ancestor: Ancestor
    ) -> None:
        assert ancestor("C", "G") == "C"
        assert ancestor("G", "E") == "E"


class TestMergeFurtherFromOneParent:
    #   A   B   C   G   H   J
    #   o---o---o---o---o---o
    #        \     /
    #         o---o---o
    #         D   E   F

    @pytest.fixture(autouse=True)
    def setup_chain(self, builder: GraphBuilder) -> None:
        b = builder
        b.chain([None, "A", "B", "C"])
        b.chain(["B", "D", "E", "F"])
        b.commit(["C", "E"], "G")
        b.chain(["G", "H", "J"])

    def test_it_finds_all_the_common_ancestors(self, ancestor: Ancestor) -> None:
        assert ancestor("J", "F") == ["B", "E"]

    def test_it_finds_the_best_common_ancestor(self, merge_base: MergeBase) -> None:
        assert merge_base("J", "F") == "E"


class TestCommitsBetweenAncestorAndMerge:
    #   A   B   C       H   J
    #   o---o---o-------o---o
    #        \         /
    #         o---o---o G
    #         D  E \
    #               o F

    @pytest.fixture(autouse=True)
    def setup_chain(self, builder: GraphBuilder) -> None:
        b = builder
        b.chain([None, "A", "B", "C"])
        b.chain(["B", "D", "E", "F"])
        b.chain(["E", "G"])
        b.commit(["C", "G"], "H")
        b.chain(["H", "J"])

    def test_it_finds_all_the_common_ancestors(self, ancestor: Ancestor) -> None:
        assert ancestor("J", "F") == ["B", "E"]

    def test_it_finds_the_best_common_ancestor(self, merge_base: MergeBase) -> None:
        assert merge_base("J", "F") == "E"


class TestStaleResultsHistory:
    #   A   B   C             H   J
    #   o---o---o-------------o---o
    #        \      E        /
    #         o-----o-------o
    #        D \     \     / G
    #           \     o   /
    #            \    F  /
    #             o-----o
    #             P     Q

    @pytest.fixture(autouse=True)
    def setup_chain(self, builder: GraphBuilder) -> None:
        b = builder
        b.chain([None, "A", "B", "C"])
        b.chain(["B", "D", "E", "F"])
        b.chain(["D", "P", "Q"])
        b.commit(["E", "Q"], "G")
        b.commit(["C", "G"], "H")
        b.chain(["H", "J"])

    def test_it_finds_the_best_common_ancestor(self, ancestor: Ancestor) -> None:
        assert ancestor("J", "F") == "E"
        assert ancestor("F", "J") == "E"


class TestManyCommonAncestors:
    #         L   M   N   P   Q   R   S   T
    #         o---o---o---o---o---o---o---o
    #        /       /       /       /
    #   o---o---o...o---o...o---o---o---o---o
    #   A   B  C \  D  E \  F  G \  H   J   K
    #             \       \       \
    #              o---o---o---o---o---o
    #              U   V   W   X   Y   Z

    @pytest.fixture(autouse=True)
    def setup_chain(self, builder: GraphBuilder) -> None:
        b = builder
        pads1 = [f"pad-1-{i}" for i in range(1, 5)]
        pads2 = [f"pad-2-{i}" for i in range(1, 5)]
        backbone = (
            [None, "A", "B", "C"]
            + pads1
            + ["D", "E"]
            + pads2
            + ["F", "G"]
            + ["H", "J", "K"]
        )

        b.chain(backbone)

        b.chain(["B", "L", "M"])
        b.commit(["M", "D"], "N")
        b.chain(["N", "P"])
        b.commit(["P", "F"], "Q")
        b.chain(["Q", "R"])
        b.commit(["R", "H"], "S")
        b.chain(["S", "T"])

        b.chain(["C", "U", "V"])
        b.commit(["V", "E"], "W")
        b.chain(["W", "X"])
        b.commit(["X", "G"], "Y")
        b.chain(["Y", "Z"])

    def test_it_finds_multiple_candidate_common_ancestors(
        self, ancestor: Ancestor
    ) -> None:
        assert ancestor("T", "Z") == ["B", "D", "G"]

    def test_it_finds_the_best_common_ancestor(self, merge_base: MergeBase) -> None:
        assert merge_base("T", "Z") == "G"
