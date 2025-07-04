import pytest
from datetime import datetime, timedelta
from pathlib import Path
import textwrap

from legit.rev_list import RevList
from tests.conftest import assert_stdout, assert_stderr, assert_status
from legit.editor import Editor


def _snapshot_workspace(repo_path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in repo_path.rglob("*"):
        if ".git" in path.parts or not path.is_file():
            continue
        result[path.relative_to(repo_path).as_posix()] = path.read_text()
    return result


def assert_workspace(repo_path: Path, expected: dict[str, str]):
    actual = _snapshot_workspace(repo_path)
    assert actual == expected, f"workspace mismatch – expected {expected}, got {actual}"


def assert_index(repo, *expected_entries):
    repo.index.load()

    actual_entries = [(str(entry.path), entry.stage) for entry in repo.index.entries.values()]

    sorted_actual = sorted(actual_entries)
    sorted_expected = sorted(list(expected_entries))

    assert sorted_actual == sorted_expected, (
        f"Index content mismatch.\n"
        f"  Expected: {sorted_expected}\n"
        f"  Actual:   {sorted_actual}"
    )

@pytest.fixture
def stub_editor(monkeypatch):
    """
    Pytest fixture to stub the Editor.edit method.
    """
    def factory(message_to_return: str):
        # CORRECTED: The signature now matches the class method call.
        # It no longer expects 'editor_instance' as the first argument.
        def fake_edit(path, command=None, *, block):
            """The fake method that will replace Editor.edit."""

            # The block needs an Editor instance to operate on.
            # We create one here to pass to it.
            if block:
                block(Editor(path, command))

            # Return the stubbed message as before.
            return message_to_return

        # The patch remains the same.
        monkeypatch.setattr(Editor, 'edit', fake_edit)

    return factory

class TestCherryPick:
    class TestWithTwoBranches:
        @pytest.fixture(autouse=True)
        def setup_branches(self, legit_cmd, commit, write_file):
            """
            Sets up a repository with 'master' and 'topic' branches based on the
            Ruby test's `before` block.
            """
            self.time = datetime.now().astimezone()

            def commit_tree(message, files):
                self.time += timedelta(seconds=10)
                for path, contents in files.items():
                    write_file(path, contents)
                legit_cmd("add", ".")
                commit(message, when=self.time)

            for message in ["one", "two", "three", "four"]:
                commit_tree(message, {"f.txt": message})

            legit_cmd("branch", "topic", "@~2")
            legit_cmd("checkout", "topic")

            commit_tree("five", {"g.txt": "five"})
            commit_tree("six", {"f.txt": "six"})
            commit_tree("seven", {"g.txt": "seven"})
            commit_tree("eight", {"g.txt": "eight"})

            legit_cmd("checkout", "master")

        def test_applies_a_commit_on_top_of_the_current_head(self, repo, repo_path, legit_cmd):
            cmd, _, _, _ = legit_cmd("cherry-pick", "topic~3")
            assert_status(cmd, 0)

            revs = [commit for (commit, path) in list(RevList(repo, ["@~3.."]).each())]
            
            assert [c.message.strip() for c in revs] == ["five", "four", "three"]
            
            assert_index(repo, ("f.txt", 0), ("g.txt", 0))
            assert_workspace(repo_path, {"f.txt": "four", "g.txt": "five"})

        def test_fails_to_apply_a_content_conflict(self, repo_path, legit_cmd, resolve_revision):
            cmd, _, _, _ = legit_cmd("cherry-pick", "topic^^")
            assert_status(cmd, 1)

            short = resolve_revision("topic^^")[:7]
            
            expected_content = textwrap.dedent(f"""\
                <<<<<<< HEAD
                four=======
                six>>>>>>> {short}... six
            """)
            assert_workspace(repo_path, {"f.txt": expected_content})
            
            cmd, _, stdout, _ = legit_cmd("status", "--porcelain")
            assert_stdout(stdout, "UU f.txt\n")
            
        def test_fails_to_apply_a_modify_delete_conflict(self, repo_path, legit_cmd):
            cmd, _, _, _ = legit_cmd("cherry-pick", "topic")
            assert_status(cmd, 1)

            assert_workspace(repo_path, {"f.txt": "four", "g.txt": "eight"})
            
            cmd, _, stdout, _ = legit_cmd("status", "--porcelain")
            assert_stdout(stdout, "DU g.txt\n")

        def test_continues_a_conflicted_cherry_pick(self, repo, repo_path, legit_cmd):
            legit_cmd("cherry-pick", "topic") # This will conflict
            legit_cmd("add", "g.txt")

            cmd, _, _, _ = legit_cmd("cherry-pick", "--continue")
            assert_status(cmd, 0)

            commits = [commit for (commit, path) in list(RevList(repo, ["@~3.."]).each())]

            assert [commits[1].oid] == commits[0].parents
            assert [c.message.strip() for c in commits] == ["eight", "four", "three"]

            assert_index(repo, ("f.txt", 0), ("g.txt", 0))
            assert_workspace(repo_path, {"f.txt": "four", "g.txt": "eight"})

        def test_commits_after_a_conflicted_cherry_pick(self, repo, legit_cmd, commit):
            legit_cmd("cherry-pick", "topic")
            legit_cmd("add", "g.txt")

            cmd, _, _, _ = legit_cmd("commit")
            assert_status(cmd, 0)
            
            commits = [commit for (commit, path) in list(RevList(repo, ["@~3.."]).each())]

            assert [commits[1].oid] == commits[0].parents
            assert [c.message.strip() for c in commits] == ["eight", "four", "three"]

        def test_applies_multiple_non_conflicting_commits(self, repo, repo_path, legit_cmd):
            cmd, _, _, _ = legit_cmd("cherry-pick", "topic~3", "topic^", "topic")
            assert_status(cmd, 0)

            revs = [commit for (commit, path) in list(RevList(repo, ["@~4.."]).each())]

            assert [c.message.strip() for c in revs] == ["eight", "seven", "five", "four"]
            
            assert_index(repo, ("f.txt", 0), ("g.txt", 0))
            assert_workspace(repo_path, {"f.txt": "four", "g.txt": "eight"})

        def test_stops_when_a_list_of_commits_includes_a_conflict(self, legit_cmd):
            cmd, _, _, _ = legit_cmd("cherry-pick", "topic^", "topic~3")
            assert_status(cmd, 1)

            cmd, _, stdout, _ = legit_cmd("status", "--porcelain")
            assert_stdout(stdout, "DU g.txt\n")

        def test_stops_when_a_range_of_commits_includes_a_conflict(self, legit_cmd):
            cmd, _, _, _ = legit_cmd("cherry-pick", "..topic")
            assert_status(cmd, 1)

            cmd, _, stdout, _ = legit_cmd("status", "--porcelain")
            assert_stdout(stdout, "UU f.txt\n")
            
        def test_refuses_to_commit_in_a_conflicted_state(self, legit_cmd):
            legit_cmd("cherry-pick", "..topic") # Creates conflict
            
            cmd, _, _, stderr = legit_cmd("commit")
            assert_status(cmd, 128)

            expected_error = textwrap.dedent("""\
                error: Committing is not possible because you have unmerged files.
                hint: Fix them up in the work tree, and then use 'legit add/rm <file>'
                hint: as appropriate to mark resolution and make a commit.
                fatal: Exiting because of an unresolved conflict.
            """)
            assert_stderr(stderr, expected_error)
            
        def test_refuses_to_continue_in_a_conflicted_state(self, legit_cmd):
            legit_cmd("cherry-pick", "..topic") # Creates conflict

            cmd, _, _, stderr = legit_cmd("cherry-pick", "--continue")
            assert_status(cmd, 128)
            
            expected_error = textwrap.dedent("""\
                error: Committing is not possible because you have unmerged files.
                hint: Fix them up in the work tree, and then use 'legit add/rm <file>'
                hint: as appropriate to mark resolution and make a commit.
                fatal: Exiting because of an unresolved conflict.
            """)
            assert_stderr(stderr, expected_error)

        def test_can_continue_after_resolving_the_conflicts(self, repo, repo_path, legit_cmd, write_file):
            legit_cmd("cherry-pick", "..topic") # Creates conflict

            write_file("f.txt", "six")
            legit_cmd("add", "f.txt")

            cmd, _, _, _ = legit_cmd("cherry-pick", "--continue")
            assert_status(cmd, 0)
            
            revs = [commit for (commit, path) in list(RevList(repo, ["@~5.."]).each())]

            assert [c.message.strip() for c in revs] == ["eight", "seven", "six", "five", "four"]
            
            assert_index(repo, ("f.txt", 0), ("g.txt", 0))
            assert_workspace(repo_path, {"f.txt": "six", "g.txt": "eight"})

        def test_can_continue_after_commiting_the_resolved_tree(self, repo, repo_path, legit_cmd, write_file, commit):
            legit_cmd("cherry-pick", "..topic") # Creates conflict

            write_file("f.txt", "six")
            legit_cmd("add", "f.txt")
            commit("six") # Manually commit resolution

            cmd, _, _, _ = legit_cmd("cherry-pick", "--continue")
            assert_status(cmd, 0)
            
            revs = [commit for (commit, path) in list(RevList(repo, ["@~5.."]).each())]

            assert [c.message.strip() for c in revs] == ["eight", "seven", "six", "five", "four"]
            
            assert_index(repo, ("f.txt", 0), ("g.txt", 0))
            assert_workspace(repo_path, {"f.txt": "six", "g.txt": "eight"})

        class TestAbortingInAConflictedState:
            @pytest.fixture(autouse=True)
            def setup_abort(self, legit_cmd):
                legit_cmd("cherry-pick", "..topic") # Creates conflict
                cmd, _, _, stderr = legit_cmd("cherry-pick", "--abort")
                self.cmd = cmd
                self.stderr = stderr
            
            def test_exits_successfully(self):
                assert_status(self.cmd, 0)
                assert_stderr(self.stderr, "")

            def test_resets_to_the_old_head(self, legit_cmd, load_commit):
                assert load_commit("HEAD").message.strip() == "four"
                
                cmd, _, stdout, _ = legit_cmd("status", "--porcelain")
                assert_stdout(stdout, "")

            def test_removes_the_merge_state(self, repo):
                # Assuming repo.pending_commit maps to the .git/CHERRY_PICK_HEAD logic
                assert not repo.pending_commit().is_in_progress()

        class TestAbortingInACommittedState:
            @pytest.fixture(autouse=True)
            def setup_abort_committed(self, legit_cmd, commit, stub_editor):
                legit_cmd("cherry-pick", "..topic") # Creates conflict
                legit_cmd("add", ".")
                
                stub_editor("picked")
                legit_cmd("commit")

                cmd, _, _, stderr = legit_cmd("cherry-pick", "--abort")
                self.cmd = cmd
                self.stderr = stderr
            
            def test_exits_with_a_warning(self):
                assert_status(self.cmd, 0)
                expected_warning = textwrap.dedent("""\
                    warning: You seem to have moved HEAD. Not rewinding, check your HEAD!
                """)
                assert_stderr(self.stderr, expected_warning)
            
            def test_does_not_reset_head(self, legit_cmd, load_commit):
                assert load_commit("HEAD").message.strip() == "picked"
                
                cmd, _, stdout, _ = legit_cmd("status", "--porcelain")
                assert_stdout(stdout, "")

            def test_removes_the_merge_state(self, repo):
                assert not repo.pending_commit().is_in_progress()

    class TestWithMerges:
        @pytest.fixture(autouse=True)
        def setup_merges(self, legit_cmd, commit, write_file):
            self.time = datetime.now().astimezone()

            def commit_tree(message, files):
                self.time += timedelta(seconds=10)
                for path, contents in files.items():
                    write_file(path, contents)
                legit_cmd("add", ".")
                commit(message, when=self.time)

            for message in ["one", "two", "three", "four"]:
                commit_tree(message, {"f.txt": message})

            legit_cmd("branch", "topic", "@~2")
            legit_cmd("checkout", "topic")
            commit_tree("five", {"g.txt": "five"})
            commit_tree("six", {"h.txt": "six"})

            legit_cmd("branch", "side", "@^")
            legit_cmd("checkout", "side")
            commit_tree("seven", {"j.txt": "seven"})
            commit_tree("eight", {"j.txt": "eight"})
            commit_tree("nine", {"f.txt": "nine"})

            legit_cmd("checkout", "topic")
            legit_cmd("merge", "side^", "-m", "merge side^")
            legit_cmd("merge", "side", "-m", "merge side")

            legit_cmd("checkout", "master")

        def test_refuses_to_cherry_pick_a_merge_without_specifying_a_parent(self, legit_cmd, resolve_revision):
            cmd, _, _, stderr = legit_cmd("cherry-pick", "topic")
            assert_status(cmd, 1)

            oid = resolve_revision("topic")

            expected_error = f"error: commit {oid} is a merge but no -m option was given\n"
            assert_stderr(stderr, expected_error)

        def test_refuses_to_cherry_pick_a_non_merge_commit_with_mainline(self, legit_cmd, resolve_revision):
            cmd, _, _, stderr = legit_cmd("cherry-pick", "-m", "1", "side")
            assert_status(cmd, 1)

            oid = resolve_revision("side")

            expected_error = f"error: mainline was specified but commit {oid} is not a merge\n"
            assert_stderr(stderr, expected_error)

        def test_cherry_picks_a_merge_based_on_its_first_parent(self, repo, repo_path, legit_cmd):
            cmd, _, _, _ = legit_cmd("cherry-pick", "-m", "1", "topic^")
            assert_status(cmd, 0)

            assert_index(repo, ("f.txt", 0), ("j.txt", 0))
            assert_workspace(repo_path, {"f.txt": "four", "j.txt": "eight"})

        def test_cherry_picks_a_merge_based_on_its_second_parent(self, repo, repo_path, legit_cmd):
            cmd, _, _, _ = legit_cmd("cherry-pick", "-m", "2", "topic^")
            assert_status(cmd, 0)

            assert_index(repo, ("f.txt", 0), ("h.txt", 0))
            assert_workspace(repo_path, {"f.txt": "four", "h.txt": "six"})

        def test_resumes_cherry_picking_merges_after_a_conflict(self, repo, repo_path, legit_cmd, write_file):
            cmd, _, _, _ = legit_cmd("cherry-pick", "-m", "1", "topic", "topic^")
            assert_status(cmd, 1)

            cmd, _, stdout, _ = legit_cmd("status", "--porcelain")
            assert_stdout(stdout, "UU f.txt\n")

            write_file("f.txt", "resolved")
            legit_cmd("add", "f.txt")
            cmd, _, _, _ = legit_cmd("cherry-pick", "--continue")
            assert_status(cmd, 0)

            revs = [commit for (commit, path) in list(RevList(repo, ["@~3.."]).each())]
            
            assert [c.message.strip() for c in revs] == ["merge side^", "merge side", "four"]
            assert_index(repo, ("f.txt", 0), ("j.txt", 0))
            assert_workspace(repo_path, {"f.txt": "resolved", "j.txt": "eight"})

