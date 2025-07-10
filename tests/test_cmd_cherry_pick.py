import textwrap
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, TypeAlias, cast

import pytest

from legit.commit import Commit as CommitObj
from legit.repository import Repository
from legit.rev_list import RevList
from tests.cmd_helpers import (
    assert_index,
    assert_status,
    assert_stderr,
    assert_stdout,
    assert_workspace,
)
from tests.conftest import (
    Commit,
    LegitCmd,
    LoadCommit,
    ResolveRevision,
    StubEditorFactory,
    WriteFile,
)

CommitTree: TypeAlias = Callable[[str, dict[str, str]], None]


class CherryPickHistorySetup:
    @pytest.fixture
    def commit_tree(
        self, write_file: WriteFile, legit_cmd: LegitCmd, commit: Commit
    ) -> CommitTree:
        def _commit_tree(message: str, files: dict[str, str]) -> None:
            self.time += timedelta(seconds=10)
            for path, contents in files.items():
                write_file(path, contents)
            legit_cmd("add", ".")
            commit(message, when=self.time)

        return _commit_tree

    @pytest.fixture(autouse=True)
    def setup(self, legit_cmd: LegitCmd, commit_tree: CommitTree) -> None:
        self.time = datetime.now().astimezone()

        for message in ["one", "two", "three", "four"]:
            commit_tree(message, {"f.txt": message})

        legit_cmd("branch", "topic", "@~2")
        legit_cmd("checkout", "topic")

        commit_tree("five", {"g.txt": "five"})
        commit_tree("six", {"f.txt": "six"})
        commit_tree("seven", {"g.txt": "seven"})
        commit_tree("eight", {"g.txt": "eight"})

        legit_cmd("checkout", "master")


class TestWithTwoBranches(CherryPickHistorySetup):
    def test_it_applies_a_commit_on_top_of_the_current_head(
        self, repo: Repository, repo_path: Path, legit_cmd: LegitCmd
    ) -> None:
        cmd, *_ = legit_cmd("cherry-pick", "topic~3")
        assert_status(cmd, 0)

        revs = [
            cast(CommitObj, commit)
            for (commit, _) in list(RevList(repo, ["@~3.."]).each())
        ]

        assert [c.message.strip() for c in revs] == ["five", "four", "three"]

        assert_index(repo, {"f.txt": "four", "g.txt": "five"})
        assert_workspace(repo_path, {"f.txt": "four", "g.txt": "five"})

    def test_it_fails_to_apply_a_content_conflict(
        self,
        repo: Repository,
        repo_path: Path,
        legit_cmd: LegitCmd,
        resolve_revision: ResolveRevision,
    ) -> None:
        cmd, *_ = legit_cmd("cherry-pick", "topic^^")
        assert_status(cmd, 1)

        short = repo.database.short_oid(resolve_revision("topic^^"))

        expected_content = textwrap.dedent(f"""\
            <<<<<<< HEAD
            four=======
            six>>>>>>> {short}... six
        """)
        assert_workspace(repo_path, {"f.txt": expected_content})

        *_, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "UU f.txt\n")

    def test_it_fails_to_apply_a_modify_delete_conflict(
        self, repo_path: Path, legit_cmd: LegitCmd
    ) -> None:
        cmd, *_ = legit_cmd("cherry-pick", "topic")
        assert_status(cmd, 1)

        assert_workspace(repo_path, {"f.txt": "four", "g.txt": "eight"})

        *_, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "DU g.txt\n")

    def test_it_continues_a_conflicted_cherry_pick(
        self, repo: Repository, repo_path: Path, legit_cmd: LegitCmd
    ) -> None:
        _ = legit_cmd("cherry-pick", "topic")
        _ = legit_cmd("add", "g.txt")

        cmd, _, _, _ = legit_cmd("cherry-pick", "--continue")
        assert_status(cmd, 0)

        commits = [
            cast(CommitObj, commit)
            for (commit, _) in list(RevList(repo, ["@~3.."]).each())
        ]

        assert [commits[1].oid] == commits[0].parents
        assert [c.message.strip() for c in commits] == ["eight", "four", "three"]

        assert_index(repo, {"f.txt": "four", "g.txt": "eight"})
        assert_workspace(repo_path, {"f.txt": "four", "g.txt": "eight"})

    def test_it_commits_after_a_conflicted_cherry_pick(
        self, repo: Repository, legit_cmd: LegitCmd
    ) -> None:
        legit_cmd("cherry-pick", "topic")
        legit_cmd("add", "g.txt")

        cmd, *_ = legit_cmd("commit")
        assert_status(cmd, 0)

        commits = [
            cast(CommitObj, commit)
            for (commit, _) in list(RevList(repo, ["@~3.."]).each())
        ]

        assert [commits[1].oid] == commits[0].parents
        assert [c.message.strip() for c in commits] == ["eight", "four", "three"]

    def test_it_applies_multiple_non_conflicting_commits(
        self, repo: Repository, repo_path: Path, legit_cmd: LegitCmd
    ) -> None:
        cmd, *_ = legit_cmd("cherry-pick", "topic~3", "topic^", "topic")
        assert_status(cmd, 0)

        revs = [
            cast(CommitObj, commit)
            for (commit, _) in list(RevList(repo, ["@~4.."]).each())
        ]

        assert [c.message.strip() for c in revs] == ["eight", "seven", "five", "four"]

        assert_index(repo, {"f.txt": "four", "g.txt": "eight"})
        assert_workspace(repo_path, {"f.txt": "four", "g.txt": "eight"})

    def test_it_stops_when_a_list_of_commits_includes_a_conflict(
        self, legit_cmd: LegitCmd
    ) -> None:
        cmd, *_ = legit_cmd("cherry-pick", "topic^", "topic~3")
        assert_status(cmd, 1)

        *_, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "DU g.txt\n")

    def test_it_stops_when_a_range_of_commits_includes_a_conflict(
        self, legit_cmd: LegitCmd
    ) -> None:
        cmd, *_ = legit_cmd("cherry-pick", "..topic")
        assert_status(cmd, 1)

        *_, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "UU f.txt\n")

    def test_it_refuses_to_commit_in_a_conflicted_state(
        self, legit_cmd: LegitCmd
    ) -> None:
        _ = legit_cmd("cherry-pick", "..topic")

        cmd, *_, stderr = legit_cmd("commit")
        assert_status(cmd, 128)

        expected_error = textwrap.dedent("""\
            error: Committing is not possible because you have unmerged files.
            hint: Fix them up in the work tree, and then use 'legit add/rm <file>'
            hint: as appropriate to mark resolution and make a commit.
            fatal: Exiting because of an unresolved conflict.
        """)
        assert_stderr(stderr, expected_error)

    def test_it_refuses_to_continue_in_a_conflicted_state(
        self, legit_cmd: LegitCmd
    ) -> None:
        _ = legit_cmd("cherry-pick", "..topic")

        cmd, *_, stderr = legit_cmd("cherry-pick", "--continue")
        assert_status(cmd, 128)

        expected_error = textwrap.dedent("""\
            error: Committing is not possible because you have unmerged files.
            hint: Fix them up in the work tree, and then use 'legit add/rm <file>'
            hint: as appropriate to mark resolution and make a commit.
            fatal: Exiting because of an unresolved conflict.
        """)
        assert_stderr(stderr, expected_error)

    def test_it_can_continue_after_resolving_the_conflicts(
        self,
        repo: Repository,
        repo_path: Path,
        legit_cmd: LegitCmd,
        write_file: WriteFile,
    ) -> None:
        _ = legit_cmd("cherry-pick", "..topic")

        write_file("f.txt", "six")
        legit_cmd("add", "f.txt")

        cmd, *_ = legit_cmd("cherry-pick", "--continue")
        assert_status(cmd, 0)

        revs = [
            cast(CommitObj, commit)
            for (commit, _) in list(RevList(repo, ["@~5.."]).each())
        ]

        assert [c.message.strip() for c in revs] == [
            "eight",
            "seven",
            "six",
            "five",
            "four",
        ]

        assert_index(repo, {"f.txt": "six", "g.txt": "eight"})
        assert_workspace(repo_path, {"f.txt": "six", "g.txt": "eight"})

    def test_it_can_continue_after_commiting_the_resolved_tree(
        self,
        repo: Repository,
        repo_path: Path,
        legit_cmd: LegitCmd,
        write_file: WriteFile,
    ) -> None:
        _ = legit_cmd("cherry-pick", "..topic")

        write_file("f.txt", "six")
        _ = legit_cmd("add", "f.txt")
        _ = legit_cmd("commit")

        cmd, *_ = legit_cmd("cherry-pick", "--continue")
        assert_status(cmd, 0)

        revs = [
            cast(CommitObj, commit)
            for (commit, _) in list(RevList(repo, ["@~5.."]).each())
        ]

        assert [c.message.strip() for c in revs] == [
            "eight",
            "seven",
            "six",
            "five",
            "four",
        ]

        assert_index(repo, {"f.txt": "six", "g.txt": "eight"})
        assert_workspace(repo_path, {"f.txt": "six", "g.txt": "eight"})


class TestAbortingInAConflictedState(CherryPickHistorySetup):
    @pytest.fixture(autouse=True)
    def setup_abort(self, legit_cmd: LegitCmd) -> None:
        legit_cmd("cherry-pick", "..topic")
        self.cmd, *_, self.stderr = legit_cmd("cherry-pick", "--abort")

    def test_it_exits_successfully(self) -> None:
        assert_status(self.cmd, 0)
        assert_stderr(self.stderr, "")

    def test_it_resets_to_the_old_head(
        self, legit_cmd: LegitCmd, load_commit: LoadCommit
    ) -> None:
        assert cast(CommitObj, load_commit("HEAD")).message.strip() == "four"

        *_, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "")

    def test_it_removes_the_merge_state(self, repo: Repository) -> None:
        assert not repo.pending_commit().is_in_progress()


class TestAbortingInACommittedState(CherryPickHistorySetup):
    @pytest.fixture(autouse=True)
    def setup_abort_committed(
        self, legit_cmd: LegitCmd, stub_editor: StubEditorFactory
    ) -> None:
        _ = legit_cmd("cherry-pick", "..topic")
        _ = legit_cmd("add", ".")

        stub_editor("picked")
        _ = legit_cmd("commit")

        self.cmd, *_, self.stderr = legit_cmd("cherry-pick", "--abort")

    def test_it_exits_with_a_warning(self) -> None:
        assert_status(self.cmd, 0)
        expected_warning = textwrap.dedent("""\
            warning: You seem to have moved HEAD. Not rewinding, check your HEAD!
        """)
        assert_stderr(self.stderr, expected_warning)

    def test_it_does_not_reset_head(
        self, legit_cmd: LegitCmd, load_commit: LoadCommit
    ) -> None:
        assert cast(CommitObj, load_commit("HEAD")).message.strip() == "picked"

        *_, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "")

    def test_it_removes_the_merge_state(self, repo: Repository) -> None:
        assert not repo.pending_commit().is_in_progress()


class TestWithMerges(CherryPickHistorySetup):
    #   f---f---f---f [master]
    #        \
    #         g---h---o---o [topic]
    #          \     /   /
    #           j---j---f [side]

    @pytest.fixture(autouse=True)
    def setup_merges(self, legit_cmd: LegitCmd, commit_tree: CommitTree) -> None:
        self.time = datetime.now().astimezone()

        for message in ["one", "two", "three", "four"]:
            commit_tree(message, {"f.txt": message})

        _ = legit_cmd("branch", "topic", "@~2")
        _ = legit_cmd("checkout", "topic")
        commit_tree("five", {"g.txt": "five"})
        commit_tree("six", {"h.txt": "six"})

        _ = legit_cmd("branch", "side", "@^")
        _ = legit_cmd("checkout", "side")
        commit_tree("seven", {"j.txt": "seven"})
        commit_tree("eight", {"j.txt": "eight"})
        commit_tree("nine", {"f.txt": "nine"})

        _ = legit_cmd("checkout", "topic")
        _ = legit_cmd("merge", "side^", "-m", "merge side^")
        _ = legit_cmd("merge", "side", "-m", "merge side")

        _ = legit_cmd("checkout", "master")

    def test_it_refuses_to_cherry_pick_a_merge_without_specifying_a_parent(
        self,
        legit_cmd: LegitCmd,
        resolve_revision: ResolveRevision,
    ) -> None:
        cmd, *_, stderr = legit_cmd("cherry-pick", "topic")
        assert_status(cmd, 1)

        oid = resolve_revision("topic")

        expected_error = f"error: commit {oid} is a merge but no -m option was given\n"
        assert_stderr(stderr, expected_error)

    def test_it_refuses_to_cherry_pick_a_non_merge_commit_with_mainline(
        self,
        legit_cmd: LegitCmd,
        resolve_revision: ResolveRevision,
    ) -> None:
        cmd, *_, stderr = legit_cmd("cherry-pick", "-m", "1", "side")
        assert_status(cmd, 1)

        oid = resolve_revision("side")

        expected_error = (
            f"error: mainline was specified but commit {oid} is not a merge\n"
        )
        assert_stderr(stderr, expected_error)

    def test_it_cherry_picks_a_merge_based_on_its_first_parent(
        self, repo: Repository, repo_path: Path, legit_cmd: LegitCmd
    ) -> None:
        cmd, *_, _ = legit_cmd("cherry-pick", "-m", "1", "topic^")
        assert_status(cmd, 0)

        assert_index(repo, {"f.txt": "four", "j.txt": "eight"})
        assert_workspace(repo_path, {"f.txt": "four", "j.txt": "eight"})

    def test_it_cherry_picks_a_merge_based_on_its_second_parent(
        self, repo: Repository, repo_path: Path, legit_cmd: LegitCmd
    ) -> None:
        cmd, *_, _ = legit_cmd("cherry-pick", "-m", "2", "topic^")
        assert_status(cmd, 0)

        assert_index(repo, {"f.txt": "four", "h.txt": "six"})
        assert_workspace(repo_path, {"f.txt": "four", "h.txt": "six"})

    def test_it_resumes_cherry_picking_merges_after_a_conflict(
        self,
        repo: Repository,
        repo_path: Path,
        legit_cmd: LegitCmd,
        write_file: WriteFile,
    ) -> None:
        cmd, *_ = legit_cmd("cherry-pick", "-m", "1", "topic", "topic^")
        assert_status(cmd, 1)

        *_, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "UU f.txt\n")

        write_file("f.txt", "resolved")
        legit_cmd("add", "f.txt")
        cmd, *_ = legit_cmd("cherry-pick", "--continue")
        assert_status(cmd, 0)

        revs = [
            cast(CommitObj, commit)
            for (commit, _) in list(RevList(repo, ["@~3.."]).each())
        ]

        assert [c.message.strip() for c in revs] == [
            "merge side^",
            "merge side",
            "four",
        ]
        assert_index(repo, {"f.txt": "resolved", "j.txt": "eight"})
        assert_workspace(repo_path, {"f.txt": "resolved", "j.txt": "eight"})
