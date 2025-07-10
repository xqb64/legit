from pathlib import Path
from typing import cast

import pytest

from legit.commit import Commit as CommitObj
from legit.repository import Repository
from tests.cmd_helpers import (
    assert_index,
    assert_stdout,
    assert_workspace,
)
from tests.conftest import (
    Commit,
    Delete,
    LegitCmd,
    WriteFile,
)


class TestWithNoHeadCommit:
    @pytest.fixture(autouse=True)
    def setup(self, write_file: WriteFile, legit_cmd: LegitCmd) -> None:
        write_file("a.txt", "1")
        write_file("outer/b.txt", "2")
        write_file("outer/inner/c.txt", "3")

        _ = legit_cmd("add", ".")

    def assert_unchanged_workspace(self, repo_path: Path) -> None:
        assert_workspace(
            repo_path,
            {
                "a.txt": "1",
                "outer/b.txt": "2",
                "outer/inner/c.txt": "3",
            },
        )

    def test_it_removes_everything_from_the_index(
        self, legit_cmd: LegitCmd, repo: Repository, repo_path: Path
    ) -> None:
        legit_cmd("reset")
        assert_index(repo, {})
        self.assert_unchanged_workspace(repo_path)

    def test_it_removes_a_single_file_from_the_index(
        self, legit_cmd: LegitCmd, repo: Repository, repo_path: Path
    ) -> None:
        legit_cmd("reset", "a.txt")
        assert_index(
            repo,
            {
                "outer/b.txt": "2",
                "outer/inner/c.txt": "3",
            },
        )
        self.assert_unchanged_workspace(repo_path)

    def test_it_removes_a_directory_from_the_index(
        self, legit_cmd: LegitCmd, repo: Repository, repo_path: Path
    ) -> None:
        legit_cmd("reset", "outer")
        assert_index(repo, {"a.txt": "1"})
        self.assert_unchanged_workspace(repo_path)


class TestWithAHeadCommit:
    @pytest.fixture(autouse=True)
    def setup(
        self,
        write_file: WriteFile,
        legit_cmd: LegitCmd,
        commit: Commit,
        repo: Repository,
    ) -> None:
        write_file("a.txt", "1")
        write_file("outer/b.txt", "2")
        write_file("outer/inner/c.txt", "3")
        _ = legit_cmd("add", ".")
        commit("first")

        write_file("outer/b.txt", "4")
        _ = legit_cmd("add", ".")
        commit("second")

        legit_cmd("rm", "a.txt")
        write_file("outer/d.txt", "5")
        write_file("outer/inner/c.txt", "6")
        _ = legit_cmd("add", ".")
        write_file("outer/e.txt", "7")

        self.head_oid = repo.refs.read_head()

    def assert_unchanged_head(self, repo: Repository) -> None:
        assert repo.refs.read_head() == self.head_oid

    def assert_unchanged_workspace(self, repo_path: Path) -> None:
        assert_workspace(
            repo_path,
            {
                "outer/b.txt": "4",
                "outer/d.txt": "5",
                "outer/e.txt": "7",
                "outer/inner/c.txt": "6",
            },
        )

    def test_it_restores_a_file_removed_from_the_index(
        self, legit_cmd: LegitCmd, repo: Repository, repo_path: Path
    ) -> None:
        _ = legit_cmd("reset", "a.txt")
        assert_index(
            repo,
            {
                "a.txt": "1",
                "outer/b.txt": "4",
                "outer/d.txt": "5",
                "outer/inner/c.txt": "6",
            },
        )
        self.assert_unchanged_head(repo)
        self.assert_unchanged_workspace(repo_path)

    def test_it_resets_a_file_modified_in_index(
        self, legit_cmd: LegitCmd, repo: Repository, repo_path: Path
    ) -> None:
        _ = legit_cmd("reset", "outer/inner")
        assert_index(
            repo,
            {
                "outer/b.txt": "4",
                "outer/d.txt": "5",
                "outer/inner/c.txt": "3",
            },
        )
        self.assert_unchanged_head(repo)
        self.assert_unchanged_workspace(repo_path)

    def test_it_removes_a_file_added_to_the_index(
        self, legit_cmd: LegitCmd, repo: Repository, repo_path: Path
    ) -> None:
        _ = legit_cmd("reset", "outer/d.txt")
        assert_index(
            repo,
            {
                "outer/b.txt": "4",
                "outer/inner/c.txt": "6",
            },
        )
        self.assert_unchanged_head(repo)
        self.assert_unchanged_workspace(repo_path)

    def test_it_resets_a_file_to_specific_commit(
        self, legit_cmd: LegitCmd, repo: Repository, repo_path: Path
    ) -> None:
        _ = legit_cmd("reset", "@^", "outer/b.txt")
        assert_index(
            repo,
            {
                "outer/b.txt": "2",
                "outer/d.txt": "5",
                "outer/inner/c.txt": "6",
            },
        )
        self.assert_unchanged_head(repo)
        self.assert_unchanged_workspace(repo_path)

    def test_it_resets_the_whole_index(
        self, legit_cmd: LegitCmd, repo: Repository, repo_path: Path
    ) -> None:
        _ = legit_cmd("reset")
        assert_index(
            repo,
            {
                "a.txt": "1",
                "outer/b.txt": "4",
                "outer/inner/c.txt": "3",
            },
        )
        self.assert_unchanged_head(repo)
        self.assert_unchanged_workspace(repo_path)

    def test_it_resets_the_index_and_moves_head(
        self, legit_cmd: LegitCmd, repo: Repository, repo_path: Path
    ) -> None:
        _ = legit_cmd("reset", "@^")
        assert_index(
            repo,
            {
                "a.txt": "1",
                "outer/b.txt": "2",
                "outer/inner/c.txt": "3",
            },
        )
        assert (
            repo.refs.read_head()
            == cast(CommitObj, repo.database.load(cast(str, self.head_oid))).parent
        )
        self.assert_unchanged_workspace(repo_path)

    def test_it_moves_head_and_leaves_the_index_unchanged(
        self, legit_cmd: LegitCmd, repo: Repository, repo_path: Path
    ) -> None:
        _ = legit_cmd("reset", "--soft", "@^")
        assert_index(
            repo,
            {
                "outer/b.txt": "4",
                "outer/d.txt": "5",
                "outer/inner/c.txt": "6",
            },
        )
        assert (
            repo.refs.read_head()
            == cast(CommitObj, repo.database.load(cast(str, self.head_oid))).parent
        )
        self.assert_unchanged_workspace(repo_path)

    def test_it_resets_the_index_and_the_workspace(
        self,
        write_file: WriteFile,
        delete: Delete,
        legit_cmd: LegitCmd,
        repo: Repository,
    ) -> None:
        write_file("a.txt/nested", "remove me")
        write_file("outer/b.txt", "10")
        delete("outer/inner")

        _ = legit_cmd("reset", "--hard")
        self.assert_unchanged_head(repo)

        assert_index(
            repo,
            {
                "a.txt": "1",
                "outer/b.txt": "4",
                "outer/inner/c.txt": "3",
            },
        )

        *_, stdout, _ = legit_cmd("status", "--porcelain")

        assert_stdout(stdout, "?? outer/e.txt\n")

    def test_it_lets_you_return_to_the_previous_state_using_orig_head(
        self, legit_cmd: LegitCmd, repo: Repository
    ) -> None:
        _ = legit_cmd("reset", "--hard", "@^")
        assert_index(
            repo,
            {
                "a.txt": "1",
                "outer/b.txt": "2",
                "outer/inner/c.txt": "3",
            },
        )
        _ = legit_cmd("reset", "--hard", "ORIG_HEAD")
        assert_index(
            repo,
            {
                "a.txt": "1",
                "outer/b.txt": "4",
                "outer/inner/c.txt": "3",
            },
        )
