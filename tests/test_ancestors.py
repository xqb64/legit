import shutil
import datetime
import pytest
from pathlib import Path

# Import your modules
from legit.database import Database
from legit.author import Author
from legit.commit import Commit
from legit.common_ancestors import CommonAncestors
from legit.bases import Bases


@pytest.fixture
def db(repo_path):
    return Database(repo_path / "objects")

class GraphBuilder:
    def __init__(self, db):
        self.db = db
        self.commits = {}

    def commit(self, parents, message):
        parent_oids = [self.commits[p] for p in parents]
        author = Author("A. U. Thor", "author@example.com", datetime.datetime.now().astimezone())
        commit = Commit(parent_oids, "0" * 40, author, author, message)
        self.db.store(commit)
        self.commits[message] = commit.oid

    def chain(self, names):
        for parent, msg in zip(names, names[1:]):
            parents = [] if parent is None else [parent]
            self.commit(parents, msg)

@pytest.fixture
def builder(db):
    return GraphBuilder(db)

@pytest.fixture
def ancestor(builder, db):
    def _ancestor(left, right):
        common = CommonAncestors(db, builder.commits[left], [builder.commits[right]])
        oids = common.find()
        msgs = [db.load(oid).message for oid in oids]
        return msgs[0] if len(msgs) == 1 else sorted(msgs)
    return _ancestor

@pytest.fixture
def merge_base(builder, db):
    def _merge_base(left, right):
        bases = Bases(db, builder.commits[left], builder.commits[right])
        oids = bases.find()
        msgs = [db.load(oid).message for oid in oids]
        return msgs[0] if len(msgs) == 1 else sorted(msgs)
    return _merge_base

# Linear history tests
class TestLinearHistory:
    @pytest.fixture(autouse=True)
    def setup_chain(self, builder):
        builder.chain([None, "A", "B", "C", "D"])

    def test_commit_with_itself(self, ancestor):
        assert ancestor("D", "D") == "D"

    def test_ancestor_of_other(self, ancestor):
        assert ancestor("B", "D") == "B"

    def test_reversed_args(self, ancestor):
        assert ancestor("D", "B") == "B"

    def test_root_commit(self, ancestor):
        assert ancestor("A", "C") == "A"

    def test_root_with_itself(self, ancestor):
        assert ancestor("A", "A") == "A"

# Forking history tests
class TestForkingHistory:
    @pytest.fixture(autouse=True)
    def setup_chain(self, builder):
        b = builder
        b.chain([None, "A", "B", "C", "D"])
        b.chain(["B", "E", "F", "G", "H"])
        b.chain(["G", "J", "K"])
        b.chain(["C", "L", "M", "N"])

    def test_nearest_fork_point(self, ancestor):
        assert ancestor("H", "K") == "G"

    def test_multiple_forks_away(self, ancestor):
        assert ancestor("D", "K") == "B"

    def test_same_fork_any_point(self, ancestor):
        assert ancestor("D", "L") == "C"
        assert ancestor("M", "D") == "C"
        assert ancestor("D", "N") == "C"

    def test_ancestor_of_other(self, ancestor):
        assert ancestor("K", "E") == "E"

    def test_root_commit(self, ancestor):
        assert ancestor("J", "A") == "A"

# Merge tests
class TestWithMerge:
    @pytest.fixture(autouse=True)
    def setup_chain(self, builder):
        b = builder
        b.chain([None, "A", "B", "C"])
        b.chain(["B", "D", "E", "F"])
        b.commit(["C", "E"], "G")
        b.chain(["G", "H"])

    def test_most_recent_common_ancestor(self, ancestor):
        assert ancestor("H", "F") == "E"

    def test_common_ancestor_merge_parents(self, ancestor):
        assert ancestor("C", "G") == "C"
        assert ancestor("G", "E") == "E"

# Merge further from one parent
class TestMergeFurtherFromOneParent:
    @pytest.fixture(autouse=True)
    def setup_chain(self, builder):
        b = builder
        b.chain([None, "A", "B", "C"])
        b.chain(["B", "D", "E", "F"])
        b.commit(["C", "E"], "G")
        b.chain(["G", "H", "J"])

    def test_all_common_ancestors(self, ancestor):
        assert ancestor("J", "F") == ["B", "E"]

    def test_best_common_ancestor(self, merge_base):
        assert merge_base("J", "F") == "E"

# Commits between common ancestor and merge
class TestCommitsBetweenAncestorAndMerge:
    @pytest.fixture(autouse=True)
    def setup_chain(self, builder):
        b = builder
        b.chain([None, "A", "B", "C"])
        b.chain(["B", "D", "E", "F"])
        b.chain(["E", "G"])
        b.commit(["C", "G"], "H")
        b.chain(["H", "J"])

    def test_all_common_ancestors(self, ancestor):
        assert ancestor("J", "F") == ["B", "E"]

    def test_best_common_ancestor(self, merge_base):
        assert merge_base("J", "F") == "E"

# Stale results history
class TestStaleResultsHistory:
    @pytest.fixture(autouse=True)
    def setup_chain(self, builder):
        b = builder
        b.chain([None, "A", "B", "C"])
        b.chain(["B", "D", "E", "F"])
        b.chain(["D", "P", "Q"])
        b.commit(["E", "Q"], "G")
        b.commit(["C", "G"], "H")
        b.chain(["H", "J"])

    def test_best_common_ancestor_bidirectional(self, ancestor):
        assert ancestor("J", "F") == "E"
        assert ancestor("F", "J") == "E"

# Many common ancestors
class TestManyCommonAncestors:
    @pytest.fixture(autouse=True)
    def setup_chain(self, builder):
        b = builder
        pads1 = [f"pad-1-{i}" for i in range(1,5)]
        pads2 = [f"pad-2-{i}" for i in range(1,5)]
        backbone = [None, "A", "B", "C"] + pads1 + ["D", "E"] + pads2 + ["F", "G"] + ["H", "J", "K"]
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

    def test_multiple_candidates(self, ancestor):
        assert ancestor("T", "Z") == ["B", "D", "G"]

    def test_best_common_ancestor(self, merge_base):
        assert merge_base("T", "Z") == "G"

