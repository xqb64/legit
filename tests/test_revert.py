from datetime import datetime, timedelta
from pathlib import Path

import pytest

from legit.editor import Editor
from legit.rev_list import RevList

from tests.cmd_helpers import (
    assert_index,
    assert_workspace,
    assert_stdout,
    assert_stderr, 
    assert_status,
)


def get_rev_list_messages(repo, *rev_specs):
    revs = [r for r, _ in list(RevList(repo, list(rev_specs)).each())]
    return [c.title_line().strip() for c in revs]


class TestRevert:
    @pytest.fixture(autouse=True)
    def setup(self, write_file, legit_cmd, commit):
        self.time = datetime.now().astimezone()

        def commit_tree(message, files):
            self.time += timedelta(seconds=10)
            for path, contents in files.items():
                write_file(path, contents)
            _ = legit_cmd("add", ".")
            commit(message, self.time)

        for message in ["one", "two", "three", "four"]:
            commit_tree(message, {"f.txt": message})
        
        commit_tree("five",  {"g.txt": "five"})
        commit_tree("six",   {"f.txt": "six"})
        commit_tree("seven", {"g.txt": "seven"})
        commit_tree("eight", {"g.txt": "eight"})

    def test_it_reverts_a_commit_on_top_of_current_head(self, legit_cmd, repo, repo_path):
        cmd, *_ = legit_cmd("revert", "@~2")
        assert_status(cmd, 0)

        messages = get_rev_list_messages(repo, "@~3..")
        assert messages == ['Revert "six"', "eight", "seven"]

        expected_state = {"f.txt": "four", "g.txt": "eight"}
        assert_index(repo, expected_state)
        assert_workspace(repo_path, expected_state)

    def test_it_fails_to_revert_a_content_conflict(self, legit_cmd, repo, repo_path, resolve_revision):
        cmd, *_ = legit_cmd("revert", "@~4")
        assert_status(cmd, 1)

        short = repo.database.short_oid(resolve_revision("@~4"))
        
        expected_f_txt = f"<<<<<<< HEAD\nsix=======\nthree>>>>>>> parent of {short}... four\n"
        assert_workspace(repo_path, {"g.txt": "eight", "f.txt": expected_f_txt})
        
        cmd, _, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "UU f.txt\n")

    def test_it_fails_to_revert_a_modify_delete_conflict(self, legit_cmd, repo_path):
        cmd, *_ = legit_cmd("revert", "@~3")
        assert_status(cmd, 1)

        assert_workspace(repo_path, {"f.txt": "six", "g.txt": "eight"})

        cmd, _, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "UD g.txt\n")

    def test_it_continues_a_conflicted_revert(self, legit_cmd, repo, repo_path):
        legit_cmd("revert", "@~3")
        legit_cmd("add", "g.txt")

        cmd, *_ = legit_cmd("revert", "--continue")
        assert_status(cmd, 0)
        
        commits = list(commit for commit, _ in RevList(repo, ["@~3.."]).each())

        assert commits[0].parents == [commits[1].oid]

        messages = [commit.title_line().strip() for commit in commits]
        assert messages == ['Revert "five"', "eight", "seven"]

        expected_state = {"f.txt": "six", "g.txt": "eight"}
        assert_index(repo, expected_state)
        assert_workspace(repo_path, expected_state)

    def test_it_commits_after_a_conflicted_revert(self, legit_cmd, repo):
        legit_cmd("revert", "@~3")
        legit_cmd("add", "g.txt")

        cmd, *_ = legit_cmd("commit")
        assert_status(cmd, 0)
        
        commits = list(commit for commit, _ in RevList(repo, ["@~3.."]).each())
        assert [commits[1].oid] == commits[0].parents

        messages = [commit.title_line().strip() for commit in commits]
        assert messages == ['Revert "five"', "eight", "seven"]

    def test_it_applies_multiple_non_conflicting_commits(self, legit_cmd, repo, repo_path):
        cmd, *_ = legit_cmd("revert", "@", "@^", "@^^")
        assert_status(cmd, 0)

        messages = get_rev_list_messages(repo, "@~4..")
        assert messages == ['Revert "six"', 'Revert "seven"', 'Revert "eight"', "eight"]

        expected_state = {"f.txt": "four", "g.txt": "five"}
        assert_index(repo, expected_state)
        assert_workspace(repo_path, expected_state)

    def test_it_stops_when_list_of_commits_includes_a_conflict(self, legit_cmd):
        cmd, *_ = legit_cmd("revert", "@^", "@")
        assert_status(cmd, 1)

        cmd, _, stdout, _ = legit_cmd("status", "--porcelain")
        
        assert_stdout(stdout, "UU g.txt\n")

    def test_it_stops_when_range_of_commits_includes_a_conflict(self, legit_cmd):
        cmd, *_ = legit_cmd("revert", "@~5..@~2")
        assert_status(cmd, 1)

        cmd, _, stdout, _ = legit_cmd("status", "--porcelain")

        assert_stdout(stdout, "UD g.txt\n")

    def test_it_refuses_to_commit_in_a_conflicted_state(self, legit_cmd):
        _ = legit_cmd("revert", "@~5..@~2")

        cmd, _, _, stderr = legit_cmd("commit")
        assert_status(cmd, 128)
        
        expected_error = (
            "error: Committing is not possible because you have unmerged files.\n"
            "hint: Fix them up in the work tree, and then use 'legit add/rm <file>'\n"
            "hint: as appropriate to mark resolution and make a commit.\n"
            "fatal: Exiting because of an unresolved conflict.\n"
        )
        assert_stderr(stderr, expected_error)

    def test_it_refuses_to_continue_in_a_conflicted_state(self, legit_cmd):
        _ = legit_cmd("revert", "@~5..@~2")

        cmd, _, _, stderr = legit_cmd("revert", "--continue")
        assert_status(cmd, 128)

        expected_error = (
            "error: Committing is not possible because you have unmerged files.\n"
            "hint: Fix them up in the work tree, and then use 'legit add/rm <file>'\n"
            "hint: as appropriate to mark resolution and make a commit.\n"
            "fatal: Exiting because of an unresolved conflict.\n"
        )
        assert_stderr(stderr, expected_error)
        
    def test_it_can_continue_after_resolving_conflicts(self, legit_cmd, write_file, repo, repo_path):
        _ = legit_cmd("revert", "@~4..@^")

        write_file("g.txt", "five")
        _ = legit_cmd("add", "g.txt")

        cmd, *_ = legit_cmd("revert", "--continue")
        assert_status(cmd, 0)
        
        messages = get_rev_list_messages(repo, "@~4..")
        assert messages == ['Revert "five"', 'Revert "six"', 'Revert "seven"', "eight"]

        assert_index(repo, {"f.txt": "four"})
        assert_workspace(repo_path, {"f.txt": "four"})

    def test_it_can_continue_after_committing_the_resolved_tree(self, legit_cmd, write_file, repo, repo_path):
        _ = legit_cmd("revert", "@~4..@^")

        write_file("g.txt", "five")
        legit_cmd("add", "g.txt")
        legit_cmd("commit")

        cmd, *_ = legit_cmd("revert", "--continue")
        assert_status(cmd, 0)
        
        messages = get_rev_list_messages(repo, "@~4..")
        assert messages == ['Revert "five"', 'Revert "six"', 'Revert "seven"', "eight"]
        
        assert_index(repo, {"f.txt": "four"})
        assert_workspace(repo_path, {"f.txt": "four"})

    class TestAbortingInConflictedState:
        @pytest.fixture(autouse=True)
        def setup_aborted_revert(self, legit_cmd):
            legit_cmd("revert", "@~5..@^")
            self.cmd, _, self.stderr, _ = legit_cmd("revert", "--abort")

        def test_it_exits_successfully(self,):
            assert_status(self.cmd, 0)
            assert_stderr(self.stderr, "")

        def test_it_resets_to_the_old_head(self, legit_cmd, load_commit):
            assert load_commit("HEAD").message.strip() == "eight"
            
            *_, stdout, _ = legit_cmd("status", "--porcelain")
            assert_stdout(stdout, "")

        def test_it_removes_the_merge_state(self, repo):
            assert not repo.pending_commit().is_in_progress()

    class TestAbortingInCommittedState:
        @pytest.fixture(autouse=True)
        def setup_committed_abort(self, legit_cmd, stub_editor):
            legit_cmd("revert", "@~5..@^")
            legit_cmd("add", ".")
            stub_editor("reverted\n")
            legit_cmd("commit")
            
            cmd, _, _, self.stderr = legit_cmd("revert", "--abort")
            self.cmd = cmd
            
        def test_it_exits_with_a_warning(self):
            assert_status(self.cmd, 0)
            assert_stderr(self.stderr, "warning: You seem to have moved HEAD. Not rewinding, check your HEAD!\n")

        def test_it_does_not_reset_head(self, legit_cmd, load_commit):
            assert load_commit("HEAD").message.strip() == "reverted"
            
            *_, stdout, _ = legit_cmd("status", "--porcelain")
            assert_stdout(stdout, "")

        def test_it_removes_the_merge_state(self, repo):
            assert not repo.pending_commit().is_in_progress()

class TestRevertWithMerges:

    #   f---f---f---o---o---h [master]
    #        \     /   /
    #         g---g---h [topic]

    @pytest.fixture(autouse=True)
    def setup_merge_history(self, write_file, legit_cmd, commit, repo_path):
        self.time = datetime.now().astimezone()
        self.repo_path = repo_path

        def commit_tree(message, files):
            self.time += timedelta(seconds=10)
            for path, contents in files.items():
                write_file(path, contents)
            legit_cmd("add", ".")
            commit(message, self.time)

        for message in ["one", "two", "three"]:
            commit_tree(message, {"f.txt": message})

        legit_cmd("branch", "topic", "@^")
        legit_cmd("checkout", "topic")

        commit_tree("four", {"g.txt": "four"})
        commit_tree("five", {"g.txt": "five"})
        commit_tree("six", {"h.txt": "six"})

        legit_cmd("checkout", "master")

        legit_cmd("merge", "topic^", "-m", "merge topic^")
        legit_cmd("merge", "topic", "-m", "merge topic")

        commit_tree("seven", {"h.txt": "seven"})

    def test_it_refuses_to_revert_a_merge_without_specifying_a_parent(self, legit_cmd, resolve_revision):
        cmd, *_, stderr = legit_cmd("revert", "@^")
        assert_status(cmd, 1)

        oid = resolve_revision("@^")
        expected_error = f"error: commit {oid} is a merge but no -m option was given\n"
        assert_stderr(stderr, expected_error)

    def test_it_refuses_to_revert_non_merge_commit_with_mainline(self, legit_cmd, resolve_revision):
        cmd, *_, stderr = legit_cmd("revert", "-m", "1", "@")
        assert_status(cmd, 1)

        oid = resolve_revision("@")
        expected_error = f"error: mainline was specified but commit {oid} is not a merge\n"
        assert_stderr(stderr, expected_error)

    def test_it_reverts_merge_based_on_first_parent(self, legit_cmd, repo):
        cmd, *_ = legit_cmd("revert", "-m", "1", "@~2")
        assert_status(cmd, 0)

        expected_state = {"f.txt": "three", "h.txt": "seven"}
        assert_index(repo, expected_state)
        assert_workspace(self.repo_path, expected_state)

    def test_it_reverts_merge_based_on_second_parent(self, legit_cmd, repo):
        cmd, *_ = legit_cmd("revert", "-m", "2", "@~2")
        assert_status(cmd, 0)

        expected_state = {
            "f.txt": "two",
            "g.txt": "five",
            "h.txt": "seven",
        }
        assert_index(repo, expected_state)
        assert_workspace(self.repo_path, expected_state)

    def test_it_resumes_reverting_merges_after_conflict(self, legit_cmd, repo):
        cmd, *_ = legit_cmd("revert", "-m", "1", "@^", "@^^")
        assert_status(cmd, 1)

        cmd, _, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "UD h.txt\n")

        legit_cmd("rm", "-f", "h.txt")
        cmd, *_ = legit_cmd("revert", "--continue")
        assert_status(cmd, 0)

        messages = get_rev_list_messages(repo, "@~3..")
        assert messages == ['Revert "merge topic^"', 'Revert "merge topic"', "seven"]

        expected_state = {"f.txt": "three"}
        assert_index(repo, expected_state)
        assert_workspace(self.repo_path, expected_state)
