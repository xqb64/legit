from typing import Callable, TypeAlias, cast

import pytest

from legit.author import Author
from legit.commit import Commit as CommitObj
from legit.repository import Repository
from legit.rev_list import RevList
from tests.conftest import (
    Commit,
    LegitCmd,
    LoadCommit,
    ResolveRevision,
    StubEditorFactory,
    WriteFile,
)

CommitChange: TypeAlias = Callable[[str], None]


@pytest.fixture
def commit_change(
    write_file: WriteFile, legit_cmd: LegitCmd, commit: Commit
) -> CommitChange:
    def _commit_change(content: str) -> None:
        write_file("file.txt", content)
        _ = legit_cmd("add", ".")
        commit(content)

    return _commit_change


class CommitSetup:
    @pytest.fixture(autouse=True)
    def setup(self, write_file: WriteFile, legit_cmd: LegitCmd, commit: Commit) -> None:
        for msg in ["first", "second", "third"]:
            write_file("file.txt", msg)
            _ = legit_cmd("add", ".")
            commit(msg)

        _ = legit_cmd("branch", "topic")
        _ = legit_cmd("checkout", "topic")


class TestOnABranch(CommitSetup):
    def test_it_advances_a_branch_pointer(
        self,
        repo: Repository,
        resolve_revision: ResolveRevision,
        commit_change: CommitChange,
    ) -> None:
        head_before = repo.refs.read_ref("HEAD")

        commit_change("change")

        head_after = repo.refs.read_ref("HEAD")
        branch_after = repo.refs.read_ref("topic")

        assert head_before != head_after
        assert head_after == branch_after

        assert head_before == resolve_revision("@^")


class TestWithADetachedHead(CommitSetup):
    @pytest.fixture(autouse=True)
    def setup_detached_head(self, legit_cmd: LegitCmd) -> None:
        _ = legit_cmd("checkout", "@")

    def test_it_advances_HEAD(
        self, repo: Repository, commit_change: CommitChange
    ) -> None:
        head_before = repo.refs.read_ref("HEAD")
        commit_change("change")
        head_after = repo.refs.read_ref("HEAD")

        assert head_before != head_after

    def test_it_does_not_advance_the_detached_branch(
        self, repo: Repository, commit_change: CommitChange
    ) -> None:
        branch_before = repo.refs.read_ref("topic")
        commit_change("change")
        branch_after = repo.refs.read_ref("topic")

        assert branch_before == branch_after

    def test_leaves_HEAD_a_commit_ahead_of_branch(
        self,
        repo: Repository,
        commit_change: CommitChange,
        resolve_revision: ResolveRevision,
    ) -> None:
        commit_change("change")

        assert repo.refs.read_ref("topic") == resolve_revision("@^")


class TestWithConcurrentBranches(CommitSetup):
    @pytest.fixture(autouse=True)
    def setup_concurrent_branches(self, legit_cmd: LegitCmd) -> None:
        _ = legit_cmd("branch", "fork", "@^")

    def test_it_advances_the_branch_from_a_shared_parent(
        self,
        legit_cmd: LegitCmd,
        commit_change: CommitChange,
        resolve_revision: ResolveRevision,
    ) -> None:
        commit_change("A")
        commit_change("B")

        _ = legit_cmd("checkout", "fork")
        commit_change("C")

        assert resolve_revision("topic") != resolve_revision("fork")
        assert resolve_revision("topic~3") == resolve_revision("fork^")


class TestConfiguringAnAuthor:
    @pytest.fixture(autouse=True)
    def setup_fake_config(self, legit_cmd: LegitCmd) -> None:
        _ = legit_cmd("config", "user.name", "A. N. User")
        _ = legit_cmd("config", "user.email", "user@example.com")

    def test_it_uses_the_author_information_from_the_config(
        self,
        write_file: WriteFile,
        legit_cmd: LegitCmd,
        commit: Commit,
        load_commit: LoadCommit,
    ) -> None:
        write_file("file.txt", "1")
        _ = legit_cmd("add", ".")
        commit("first", None, False)

        head = cast(CommitObj, load_commit("@"))

        assert "A. N. User" == cast(Author, head.author).name
        assert "user@example.com" == cast(Author, head.author).email


class TestReusingMessages:
    @pytest.fixture(autouse=True)
    def setup_one_commit(
        self, write_file: WriteFile, legit_cmd: LegitCmd, commit: Commit
    ) -> None:
        write_file("file.txt", "1")
        legit_cmd("add", ".")
        commit("first")

    def test_it_uses_the_message_from_another_commit(
        self, write_file: WriteFile, legit_cmd: LegitCmd, repo: Repository
    ) -> None:
        write_file("file.txt", "2")
        _ = legit_cmd("add", ".")
        _ = legit_cmd("commit", "-C", "@")

        messages = [
            cast(CommitObj, c).message.strip()
            for (c, _) in list(RevList(repo, ["HEAD"]).each())
        ]
        assert messages == ["first", "first"]


class TestAmendingCommits:
    @pytest.fixture(autouse=True)
    def setup_three_commits(
        self, write_file: WriteFile, legit_cmd: LegitCmd, commit: Commit
    ) -> None:
        for msg in ["first", "second", "third"]:
            write_file("file.txt", msg)
            _ = legit_cmd("add", ".")
            commit(msg)

    def test_it_replaces_the_last_commit_message(
        self, repo: Repository, legit_cmd: LegitCmd, stub_editor: StubEditorFactory
    ) -> None:
        stub_editor("third [amended]\n")
        _ = legit_cmd("commit", "--amend")
        messages = [
            cast(CommitObj, c).message.strip()
            for (c, _) in list(RevList(repo, ["HEAD"]).each())
        ]
        assert messages == ["third [amended]", "second", "first"]

    def test_it_replaces_the_last_commit_tree(
        self,
        write_file: WriteFile,
        legit_cmd: LegitCmd,
        load_commit: LoadCommit,
        repo: Repository,
    ) -> None:
        write_file("another.txt", "1")
        _ = legit_cmd("add", "another.txt")
        _ = legit_cmd("commit", "--amend")

        commit = cast(CommitObj, load_commit("HEAD"))
        diff = repo.database.tree_diff(cast(str, commit.parent), commit.oid)

        paths = sorted(str(p) for p in diff.keys())
        assert paths == ["another.txt", "file.txt"]
