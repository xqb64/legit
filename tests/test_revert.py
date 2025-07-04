import pytest
from pathlib import Path
from datetime import datetime, timedelta

from legit.editor import Editor
from legit.rev_list import RevList
from tests.conftest import assert_stdout, assert_stderr, assert_status


def assert_index(repo, expected_entries):
    files = {}

    repo.index.load()

    for entry in repo.index.entries.values():
        files[str(entry.path)] = repo.database.load(entry.oid).data

    assert files, expected_entries


@pytest.fixture
def stub_editor(monkeypatch):
    def factory(message_to_return: str):
        def fake_edit(path, command=None, *, block):
            if block:
                block(Editor(path, command))

            return message_to_return

        monkeypatch.setattr(Editor, 'edit', fake_edit)

    return factory


def get_rev_list_messages(repo, *rev_specs):
    """
    Gets a list of commit messages for a given revision range using RevList,
    emulating the behavior of the helper in the Ruby tests.
    """
    revs = list(RevList(repo, list(rev_specs)).each())
    return [c.title_line().strip() for c in revs]

def _snapshot_workspace(repo_path: Path) -> dict[str, str]:
    """Return a {relative_path: contents} mapping for every *file* in the repo.

    The `.git` directory is purposely ignored.
    """
    result: dict[str, str] = {}
    for path in repo_path.rglob("*"):
        if ".git" in path.parts or not path.is_file():
            continue
        result[path.relative_to(repo_path).as_posix()] = path.read_text()
    return result


def assert_workspace(repo_path: Path, expected: dict[str, str]):
    """Assert that the working directory exactly matches *expected*."""
    actual = _snapshot_workspace(repo_path)
    assert actual == expected, f"workspace mismatch – expected {expected}, got {actual}"


class TestRevert:
    """
    Tests for the `legit revert` command.
    """

    @pytest.fixture(autouse=True)
    def setup_commit_chain(self, write_file, legit_cmd, commit):
        """
        Sets up a standard chain of commits before each test in this class.
        This corresponds to the `before do` block in the Ruby `describe` block.
        """
        self.time = datetime.now()

        def commit_tree(message, files):
            self.time += timedelta(seconds=10)
            for path, contents in files.items():
                write_file(path, contents)
            legit_cmd("add", ".")
            commit(message, self.time)

        for message in ["one", "two", "three", "four"]:
            commit_tree(message, {"f.txt": message})
        
        commit_tree("five",  {"g.txt": "five"})
        commit_tree("six",   {"f.txt": "six"})
        commit_tree("seven", {"g.txt": "seven"})
        commit_tree("eight", {"g.txt": "eight"})

    def test_reverts_a_commit_on_top_of_current_head(self, legit_cmd, repo, repo_path):
        cmd, _, _, _ = legit_cmd("revert", "@~2")
        assert_status(cmd, 0)

        messages = get_rev_list_messages(repo, "@~3..")
        assert messages == ['Revert "six"', "eight", "seven"]

        expected_state = {"f.txt": "four", "g.txt": "eight"}
        assert_index(repo, expected_state)
        assert_workspace(repo_path, expected_state)

    def test_fails_to_revert_a_content_conflict(self, legit_cmd, repo, repo_path, resolve_revision):
        cmd, _, _, _ = legit_cmd("revert", "@~4")
        assert_status(cmd, 1)

        short = repo.database.short_oid(resolve_revision("@~4"))
        
        expected_f_txt = f"<<<<<<< HEAD\nsix=======\nthree>>>>>>> parent of {short}... four\n"
        assert_workspace(repo_path, {"g.txt": "eight", "f.txt": expected_f_txt})
        
        cmd, _, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "UU f.txt\n")

    def test_fails_to_revert_a_modify_delete_conflict(self, legit_cmd, repo_path):
        cmd, _, _, _ = legit_cmd("revert", "@~3")
        assert_status(cmd, 1)

        assert_workspace(repo_path, {"f.txt": "six", "g.txt": "eight"})

        cmd, _, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "UD g.txt\n")

    def test_continues_a_conflicted_revert(self, legit_cmd, repo, load_commit, repo_path):
        legit_cmd("revert", "@~3")  # This will conflict
        legit_cmd("add", "g.txt")   # Resolve conflict

        cmd, _, _, _ = legit_cmd("revert", "--continue")
        assert_status(cmd, 0)

        head = load_commit("HEAD")
        head_parent = load_commit("HEAD^")
        assert [head_parent.oid] == head.parents
        
        messages = get_rev_list_messages(repo, "@~3..")
        assert messages == ['Revert "five"', "eight", "seven"]

        expected_state = {"f.txt": "six", "g.txt": "eight"}
        assert_index(repo, expected_state)
        assert_workspace(repo_path, expected_state)

    def test_commits_after_a_conflicted_revert(self, legit_cmd, repo, load_commit, stub_editor):
        legit_cmd("revert", "@~3") # This will conflict
        legit_cmd("add", "g.txt")  # Resolve conflict

        stub_editor('Revert "five"\n')
        cmd, _, _, _ = legit_cmd("commit")
        assert_status(cmd, 0)

        head = load_commit("HEAD")
        head_parent = load_commit("HEAD^")
        assert [head_parent.oid] == head.parents

        messages = get_rev_list_messages(repo, "@~3..")
        assert messages == ['Revert "five"', "eight", "seven"]

    def test_applies_multiple_non_conflicting_commits(self, legit_cmd, repo, repo_path):
        cmd, _, _, _ = legit_cmd("revert", "@", "@^", "@^^")
        assert_status(cmd, 0)

        messages = get_rev_list_messages(repo, "@~4..")
        assert messages == ['Revert "six"', 'Revert "seven"', 'Revert "eight"', "eight"]

        expected_state = {"f.txt": "four", "g.txt": "five"}
        assert_index(repo, expected_state)
        assert_workspace(repo_path, expected_state)

    def test_stops_when_list_of_commits_includes_a_conflict(self, legit_cmd):
        cmd, _, _, _ = legit_cmd("revert", "@^", "@") # Reverting 'seven' is fine, but 'eight' then conflicts
        assert_status(cmd, 1)

        cmd, _, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "UU g.txt\n")

    def test_stops_when_range_of_commits_includes_a_conflict(self, legit_cmd):
        cmd, _, _, _ = legit_cmd("revert", "@~5..@~2")
        assert_status(cmd, 1)

        cmd, _, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "UD g.txt\n")

    def test_refuses_to_commit_in_a_conflicted_state(self, legit_cmd):
        legit_cmd("revert", "@~5..@~2") # Creates a conflict

        cmd, _, _, stderr = legit_cmd("commit")
        assert_status(cmd, 128)
        
        expected_error = (
            "error: Committing is not possible because you have unmerged files.\n"
            "hint: Fix them up in the work tree, and then use 'legit add/rm <file>'\n"
            "hint: as appropriate to mark resolution and make a commit.\n"
            "fatal: Exiting because of an unresolved conflict.\n"
        )
        assert_stderr(stderr, expected_error)

    def test_refuses_to_continue_in_a_conflicted_state(self, legit_cmd):
        legit_cmd("revert", "@~5..@~2") # Creates a conflict

        cmd, _, _, stderr = legit_cmd("revert", "--continue")
        assert_status(cmd, 128)

        expected_error = (
            "error: Committing is not possible because you have unmerged files.\n"
            "hint: Fix them up in the work tree, and then use 'legit add/rm <file>'\n"
            "hint: as appropriate to mark resolution and make a commit.\n"
            "fatal: Exiting because of an unresolved conflict.\n"
        )
        assert_stderr(stderr, expected_error)
        
    def test_can_continue_after_resolving_conflicts(self, legit_cmd, write_file, repo, repo_path):
        legit_cmd("revert", "@~4..@^")

        write_file("g.txt", "five")
        legit_cmd("add", "g.txt")

        cmd, _, _, _ = legit_cmd("revert", "--continue")
        assert_status(cmd, 0)
        
        messages = get_rev_list_messages(repo, "@~4..")
        assert messages == ['Revert "five"', 'Revert "six"', 'Revert "seven"', "eight"]

        assert_index(repo, {"f.txt": "four"})
        assert_workspace(repo_path, {"f.txt": "four"})

    def test_can_continue_after_committing_the_resolved_tree(self, legit_cmd, write_file, repo, repo_path):
        legit_cmd("revert", "@~4..@^")

        write_file("g.txt", "five")
        legit_cmd("add", "g.txt")
        legit_cmd("commit")

        cmd, _, _, _ = legit_cmd("revert", "--continue")
        assert_status(cmd, 0)
        
        messages = get_rev_list_messages(repo, "@~4..")
        assert messages == ['Revert "five"', 'Revert "six"', 'Revert "seven"', "eight"]
        
        assert_index(repo, {"f.txt": "four"})
        assert_workspace(repo_path, {"f.txt": "four"})

    class TestAbortingInConflictedState:
        @pytest.fixture(autouse=True)
        def setup_aborted_revert(self, legit_cmd):
            legit_cmd("revert", "@~5..@^") # Creates conflict
            cmd, _, self.stderr, _ = legit_cmd("revert", "--abort")
            self.cmd = cmd

        def test_exits_successfully(self,):
            assert_status(self.cmd, 0)
            assert_stderr(self.stderr, "")

        def test_resets_to_the_old_head(self, legit_cmd, load_commit):
            assert load_commit("HEAD").message.strip() == "eight"
            
            cmd, _, stdout, _ = legit_cmd("status", "--porcelain")
            assert_stdout(stdout, "")

        def test_removes_the_merge_state(self, repo):
            assert not repo.pending_commit().is_in_progress()

    class TestAbortingInCommittedState:
        @pytest.fixture(autouse=True)
        def setup_committed_abort(self, legit_cmd, stub_editor):
            legit_cmd("revert", "@~5..@^") # Creates conflict
            legit_cmd("add", ".")
            stub_editor("reverted\n")
            legit_cmd("commit")
            
            cmd, _, _, self.stderr = legit_cmd("revert", "--abort")
            self.cmd = cmd
            
        def test_exits_with_a_warning(self):
            assert_status(self.cmd, 0)
            assert_stderr(self.stderr, "warning: You seem to have moved HEAD. Not rewinding, check your HEAD!\n")

        def test_does_not_reset_head(self, legit_cmd, load_commit):
            assert load_commit("HEAD").message.strip() == "reverted"
            
            cmd, _, stdout, _ = legit_cmd("status", "--porcelain")
            assert_stdout(stdout, "")

        def test_removes_the_merge_state(self, repo):
            assert not repo.pending_commit().is_in_progress()

class TestRevertWithMerges:
    """
    Tests for `legit revert` with merge commits.
    """

    @pytest.fixture(autouse=True)
    def setup_merge_history(self, write_file, legit_cmd, commit, repo_path):
        """
        Sets up a repository with a master and topic branch, including merges.

        History created:
          f---f---f---o---o---h [master]
                  \\     /   /
                  g---g---h [topic]
        """
        self.time = datetime.now()
        self.repo_path = repo_path

        def commit_tree(message, files):
            self.time += timedelta(seconds=10)
            for path, contents in files.items():
                write_file(path, contents)
            legit_cmd("add", ".")
            commit(message, self.time)

        # Create initial commits on master
        for message in ["one", "two", "three"]:
            commit_tree(message, {"f.txt": message})

        # Create and switch to topic branch
        legit_cmd("branch", "topic", "@^")
        legit_cmd("checkout", "topic")

        # Create commits on topic branch
        commit_tree("four", {"g.txt": "four"})
        commit_tree("five", {"g.txt": "five"})
        commit_tree("six", {"h.txt": "six"})

        # Switch back to master and merge
        legit_cmd("checkout", "master")
        legit_cmd("merge", "topic^", "-m", "merge topic^")
        legit_cmd("merge", "topic", "-m", "merge topic")

        # Final commit on master
        commit_tree("seven", {"h.txt": "seven"})

    def test_refuses_to_revert_merge_without_mainline(self, legit_cmd, resolve_revision):
        """Corresponds to: 'refuses to revert a merge without specifying a parent'"""
        cmd, _, _, stderr = legit_cmd("revert", "@^")
        assert_status(cmd, 1)

        oid = resolve_revision("@^")
        expected_error = f"error: commit {oid} is a merge but no -m option was given\n"
        assert_stderr(stderr, expected_error)

    def test_refuses_to_revert_non_merge_with_mainline(self, legit_cmd, resolve_revision):
        """Corresponds to: 'refuses to revert a non-merge commit with mainline'"""
        cmd, _, _, stderr = legit_cmd("revert", "-m", "1", "@")
        assert_status(cmd, 1)

        oid = resolve_revision("@")
        expected_error = f"error: mainline was specified but commit {oid} is not a merge\n"
        assert_stderr(stderr, expected_error)

    def test_reverts_merge_based_on_first_parent(self, legit_cmd, repo):
        """Corresponds to: 'reverts a merge based on its first parent'"""
        cmd, _, _, _ = legit_cmd("revert", "-m", "1", "@~2")
        assert_status(cmd, 0)

        expected_state = {"f.txt": "three", "h.txt": "seven"}
        assert_index(repo, expected_state)
        assert_workspace(self.repo_path, expected_state)

    def test_reverts_merge_based_on_second_parent(self, legit_cmd, repo):
        """Corresponds to: 'reverts a merge based on its second parent'"""
        cmd, _, _, _ = legit_cmd("revert", "-m", "2", "@~2")
        assert_status(cmd, 0)

        expected_state = {
            "f.txt": "two",
            "g.txt": "five",
            "h.txt": "seven",
        }
        assert_index(repo, expected_state)
        assert_workspace(self.repo_path, expected_state)

    def test_resumes_reverting_merges_after_conflict(self, legit_cmd, repo):
        """Corresponds to: 'resumes reverting merges after a conflict'"""
        cmd, _, _, _ = legit_cmd("revert", "-m", "1", "@^", "@^^")
        assert_status(cmd, 1)

        cmd, _, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "UD h.txt\n")

        # Resolve conflict and continue
        legit_cmd("rm", "-f", "h.txt")
        cmd, _, _, _ = legit_cmd("revert", "--continue")
        assert_status(cmd, 0)

        # Check commit history
        messages = get_rev_list_messages(repo, "@~3..")
        assert messages == ['Revert "merge topic^"', 'Revert "merge topic"', "seven"]

        # Check final state
        expected_state = {"f.txt": "three"}
        assert_index(repo, expected_state)
        assert_workspace(self.repo_path, expected_state)
