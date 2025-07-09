import enum
import textwrap
from pathlib import Path

import pytest

from tests.cmd_helpers import (
    assert_stdout,
    assert_stderr,
    assert_workspace,
)


class FileMode(enum.Enum):
    EXECUTABLE = enum.auto()


@pytest.fixture
def commit_tree(write_file, legit_cmd, commit, delete, make_executable):
    def _commit_tree(msg: str, files: dict[str, str]):
        for path, contents in files.items():
            if contents != FileMode.EXECUTABLE:
                delete(path)

            if isinstance(contents, str):
                write_file(path, contents)
            elif contents == FileMode.EXECUTABLE:
                make_executable(path)
            elif isinstance(contents, list):
                write_file(path, contents[0])
                make_executable(path)

        delete(".git/index")
        _ = legit_cmd("add", ".")
        commit(msg)

    return _commit_tree


#   A   B   M
#   o---o---o [master]
#    \     /
#     `---o [topic]
#         C
#
@pytest.fixture
def merge3(commit_tree, legit_cmd):
    def _merge3(base, left, right):
        commit_tree("A", base)
        commit_tree("B", left)

        _ = legit_cmd("branch", "topic", "master^")
        _ = legit_cmd("checkout", "topic")
        commit_tree("C", right)

        _ = legit_cmd("checkout", "master")
        cmd, stdin, stdout, stderr = legit_cmd("merge", "topic", "-m", "M")
        return cmd, stdin, stdout, stderr

    return _merge3


def assert_clean_merge(legit_cmd, load_commit):
    *_, stdout, _ = legit_cmd("status", "--porcelain")
    assert_stdout(stdout, "")

    commit = load_commit("@")
    old_head = load_commit("@^")
    merge_head = load_commit("topic")

    assert commit.message.strip() == "M"
    assert commit.parents == [old_head.oid, merge_head.oid]


def assert_no_merge(load_commit):
    commit = load_commit("@")
    assert commit.message.strip() == "B"
    assert len(commit.parents) == 1


def assert_index(repo, *expected):
    repo.index.load()

    actual = sorted(
        list((str(entry.path), entry.stage) for entry in repo.index.entries.values())
    )

    assert actual == sorted(expected), (
        f"Index content mismatch.\n  Expected: {expected}\n  Actual:   {actual}"
    )


@pytest.fixture
def assert_executable(repo_path):
    def _assert_executable(path: str | Path):
        full = (repo_path / path).resolve()
        mode = full.stat().st_mode
        assert mode & 0o111, f"{path} is not executable"

    return _assert_executable


class TestMergingAnAncestor:
    @pytest.fixture(autouse=True)
    def setup(self, commit_tree, legit_cmd):
        commit_tree("A", {"f.txt": "1"})
        commit_tree("B", {"f.txt": "2"})
        commit_tree("C", {"f.txt": "3"})

        self.cmd, self.stdin, self.stdout, self.stderr = legit_cmd("merge", "@^")

    def test_it_prints_the_up_to_date_message(self):
        assert_stdout(self.stdout, "Already up to date.\n")

    def test_it_does_not_change_repository_state(self, legit_cmd, load_commit):
        commit = load_commit("@")
        assert commit.message.strip() == "C"

        *_, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "")


class TestFastForwardMerge:
    @pytest.fixture(autouse=True)
    def setup(self, commit_tree, legit_cmd):
        commit_tree("A", {"f.txt": "1"})
        commit_tree("B", {"f.txt": "2"})
        commit_tree("C", {"f.txt": "3"})

        _ = legit_cmd("branch", "topic", "@^^")
        _ = legit_cmd("checkout", "topic")

        self.cmd, self.stdin, self.stdout, self.stderr = legit_cmd(
            "merge", "master", "-m", "M"
        )

    def test_it_prints_the_fast_forward_message(self, repo, resolve_revision):
        a, b = map(resolve_revision, ["master^^", "master"])
        expected = textwrap.dedent(
            f"""\
            Updating {repo.database.short_oid(a)}..{repo.database.short_oid(b)}
            Fast-forward
            """
        )
        assert_stdout(self.stdout, expected)

    def test_it_updates_the_current_branch_head(self, load_commit, legit_cmd):
        commit = load_commit("@")
        assert commit.message.strip() == "C"

        *_, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "")


class TestUnconflictedMergeWithTwoFiles:
    @pytest.fixture(autouse=True)
    def setup(self, merge3):
        merge3(
            {"f.txt": "1", "g.txt": "1"},
            {
                "f.txt": "2",
            },
            {"g.txt": "2"},
        )

    def test_it_puts_the_combined_changes_in_the_workspace(self, repo_path):
        assert_workspace(
            repo_path,
            {
                "f.txt": "2",
                "g.txt": "2",
            },
        )

    def test_it_creates_a_clean_merge(self, legit_cmd, load_commit):
        assert_clean_merge(legit_cmd, load_commit)


class TestUnconflictedMergeWithDeletedFile:
    @pytest.fixture(autouse=True)
    def setup(self, merge3):
        merge3(
            {"f.txt": "1", "g.txt": "1"},
            {"f.txt": "2"},
            {"g.txt": None},
        )

    def test_it_puts_the_combined_changes_in_the_workspace(self, repo_path):
        assert_workspace(
            repo_path,
            {
                "f.txt": "2",
            },
        )

    def test_it_creates_a_clean_merge(self, legit_cmd, load_commit):
        assert_clean_merge(legit_cmd, load_commit)


class TestUnconflictedMergeSameAdditionOnBothSides:
    @pytest.fixture(autouse=True)
    def setup(self, merge3):
        merge3(
            {"f.txt": "1"},
            {"g.txt": "2"},
            {"g.txt": "2"},
        )

    def test_it_puts_the_combined_changes_in_the_workspace(self, repo_path):
        assert_workspace(
            repo_path,
            {
                "f.txt": "1",
                "g.txt": "2",
            },
        )

    def test_it_creates_a_clean_merge(self, legit_cmd, load_commit):
        assert_clean_merge(legit_cmd, load_commit)


class TestUnconflictedMergeSameEditOnBothSides:
    @pytest.fixture(autouse=True)
    def setup(self, merge3):
        merge3(
            {"f.txt": "1"},
            {"f.txt": "2"},
            {"f.txt": "2"},
        )

    def test_it_puts_the_combined_changes_in_the_workspace(self, repo_path):
        assert_workspace(repo_path, {"f.txt": "2"})

    def test_it_creates_a_clean_merge(self, legit_cmd, load_commit):
        assert_clean_merge(legit_cmd, load_commit)


class TestUnconflictedMergeEditAndModeChange:
    @pytest.fixture(autouse=True)
    def setup(self, merge3):
        merge3(
            {"f.txt": "1"},
            {"f.txt": "2"},
            {"f.txt": FileMode.EXECUTABLE},
        )

    def test_it_puts_the_combined_changes_in_the_workspace(
        self, repo_path, assert_executable
    ):
        assert_workspace(repo_path, {"f.txt": "2"})
        assert_executable("f.txt")

    def test_it_creates_a_clean_merge(self, legit_cmd, load_commit):
        assert_clean_merge(legit_cmd, load_commit)


class TestUnconflictedMergeModeChangeAndEdit:
    @pytest.fixture(autouse=True)
    def setup(self, merge3):
        merge3(
            {"f.txt": "1"},
            {"f.txt": FileMode.EXECUTABLE},
            {"f.txt": "3"},
        )

    def test_it_puts_the_combined_changes_in_the_workspace(
        self, repo_path, assert_executable
    ):
        assert_workspace(repo_path, {"f.txt": "3"})
        assert_executable("f.txt")

    def test_it_creates_a_clean_merge(self, legit_cmd, load_commit):
        assert_clean_merge(legit_cmd, load_commit)


class TestUnconflictedMergeSameDeletionOnBothSides:
    @pytest.fixture(autouse=True)
    def setup(self, merge3):
        merge3(
            {"f.txt": "1", "g.txt": "1"},
            {"g.txt": None},
            {"g.txt": None},
        )

    def test_it_puts_the_combined_changes_in_the_workspace(self, repo_path):
        assert_workspace(repo_path, {"f.txt": "1"})

    def test_it_creates_a_clean_merge(self, legit_cmd, load_commit):
        assert_clean_merge(legit_cmd, load_commit)


class TestUnconflictedMergeDeleteAddParent:
    @pytest.fixture(autouse=True)
    def setup(self, merge3):
        merge3(
            {"nest/f.txt": "1"},
            {"nest/f.txt": None},
            {"nest": "3"},
        )

    def test_it_puts_the_combined_changes_in_the_workspace(self, repo_path):
        assert_workspace(repo_path, {"nest": "3"})

    def test_it_creates_a_clean_merge(self, legit_cmd, load_commit):
        assert_clean_merge(legit_cmd, load_commit)


class TestUnconflictedMergeDeleteAddChild:
    @pytest.fixture(autouse=True)
    def setup(self, merge3):
        merge3(
            {"nest/f.txt": "1"},
            {"nest/f.txt": None},
            {"nest/f.txt": None, "nest/f.txt/g.txt": "3"},
        )

    def test_it_puts_the_combined_changes_in_the_workspace(self, repo_path):
        assert_workspace(repo_path, {"nest/f.txt/g.txt": "3"})

    def test_it_creates_a_clean_merge(self, legit_cmd, load_commit):
        assert_clean_merge(legit_cmd, load_commit)


class TestUnconflictedMergeInFileMergePossible:
    @pytest.fixture(autouse=True)
    def setup(self, merge3):
        merge3(
            {"f.txt": "1\n2\n3\n"},
            {"f.txt": "4\n2\n3\n"},
            {"f.txt": "1\n2\n5\n"},
        )

    def test_it_puts_the_combined_changes_in_the_workspace(self, repo_path):
        assert_workspace(repo_path, {"f.txt": "4\n2\n5\n"})

    def test_it_creates_a_clean_merge(self, legit_cmd, load_commit):
        assert_clean_merge(legit_cmd, load_commit)


class TestConflictedMergeAddAdd:
    @pytest.fixture(autouse=True)
    def setup(self, merge3):
        self.cmd, self.stdin, self.stdout, self.stderr = merge3(
            {"f.txt": "1"},
            {"g.txt": "2\n"},
            {"g.txt": "3\n"},
        )

    def test_it_prints_the_merge_conflicts(self):
        expected = textwrap.dedent(
            """\
            Auto-merging g.txt
            CONFLICT (add/add): Merge conflict in g.txt
            Automatic merge failed; fix conflicts and then commit the result.
            """
        )
        assert_stdout(self.stdout, expected)

    def test_it_puts_the_conflicted_file_in_the_workspace(self, repo_path):
        assert_workspace(
            repo_path,
            {
                "f.txt": "1",
                "g.txt": textwrap.dedent(
                    """<<<<<<< HEAD\n2\n=======\n3\n>>>>>>> topic\n""",
                ),
            },
        )

    def test_it_records_the_conflict_in_the_index(self, repo):
        assert_index(
            repo,
            ("f.txt", 0),
            ("g.txt", 2),
            ("g.txt", 3),
        )

    def test_it_does_not_write_a_merge_commit(self, load_commit):
        assert_no_merge(load_commit)

    def test_it_reports_the_conflict_in_the_status(self, legit_cmd):
        *_, stdout, _ = legit_cmd("status", "--porcelain")
        expected = "AA g.txt\n"
        assert_stdout(stdout, expected)

    def test_shows_combined_diff_against_stages_2_and_3(self, legit_cmd):
        *_, stdout, _ = legit_cmd("diff")

        expected = (
            "diff --cc g.txt\n"
            "index 0cfbf08,00750ed..2603ab2\n"
            "--- a/g.txt\n"
            "+++ b/g.txt\n"
            "@@@ -1,1 -1,1 +1,5 @@@\n"
            "++<<<<<<< HEAD\n"
            " +2\n"
            "++=======\n"
            "+ 3\n"
            "++>>>>>>> topic\n"
        )

        assert_stdout(stdout, expected)

    def test_it_shows_the_diff_against_our_version(self, legit_cmd):
        *_, stdout, _ = legit_cmd("diff", "--ours")
        expected = textwrap.dedent(
            """\
            * Unmerged path g.txt
            diff --git a/g.txt b/g.txt
            index 0cfbf08..2603ab2 100644
            --- a/g.txt
            +++ b/g.txt
            @@ -1,1 +1,5 @@
            +<<<<<<< HEAD
             2
            +=======
            +3
            +>>>>>>> topic
            """
        )
        assert_stdout(stdout, expected)

    def test_it_shows_the_diff_against_their_version(self, legit_cmd):
        *_, stdout, _ = legit_cmd("diff", "--theirs")
        expected = textwrap.dedent(
            """\
            * Unmerged path g.txt
            diff --git a/g.txt b/g.txt
            index 00750ed..2603ab2 100644
            --- a/g.txt
            +++ b/g.txt
            @@ -1,1 +1,5 @@
            +<<<<<<< HEAD
            +2
            +=======
             3
            +>>>>>>> topic
            """
        )
        assert_stdout(stdout, expected)


class TestConflictedMergeAddAddModeConflict:
    @pytest.fixture(autouse=True)
    def setup(self, merge3):
        self.cmd, self.stdin, self.stdout, self.stderr = merge3(
            {"f.txt": "1"}, {"g.txt": "2"}, {"g.txt": ["2"]}
        )

    def test_it_prints_the_merge_conflicts(self):
        expected = textwrap.dedent("""\
            Auto-merging g.txt
            CONFLICT (add/add): Merge conflict in g.txt
            Automatic merge failed; fix conflicts and then commit the result.
        """)
        assert_stdout(self.stdout, expected)

    def test_it_puts_the_conflicted_file_in_the_workspace(self, repo_path):
        assert_workspace(
            repo_path,
            {
                "f.txt": "1",
                "g.txt": "2",
            },
        )

    def test_it_records_the_conflict_in_the_index(self, repo):
        assert_index(
            repo,
            ("f.txt", 0),
            ("g.txt", 2),
            ("g.txt", 3),
        )

    def test_it_does_not_write_a_merge_commit(self, load_commit):
        assert_no_merge(load_commit)

    def test_shows_combined_diff_against_stages_2_and_3(self, legit_cmd):
        *_, stdout, _ = legit_cmd("diff")

        expected = (
            "diff --cc g.txt\n"
            "index d8263ee,d8263ee..d8263ee\n"
            "mode 100644,100755..100644\n"
            "--- a/g.txt\n"
            "+++ b/g.txt\n"
        )

        assert_stdout(stdout, expected)

    def test_it_reports_the_conflict_in_the_status(self, legit_cmd):
        *_, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "AA g.txt\n")

    def test_shows_combined_diff_modes_against_stages_2_and_3(self, legit_cmd):
        *_, stdout, _ = legit_cmd("diff")

        expected = (
            "diff --cc g.txt\n"
            "index d8263ee,d8263ee..d8263ee\n"
            "mode 100644,100755..100644\n"
            "--- a/g.txt\n"
            "+++ b/g.txt\n"
        )

        assert_stdout(stdout, expected)

    def test_it_reports_the_mode_change_in_the_appropriate_diff(self, legit_cmd):
        *_, stdout, _ = legit_cmd("diff", "-2")
        assert_stdout(stdout, "* Unmerged path g.txt\n")

        *_, stdout, _ = legit_cmd("diff", "-3")
        expected = textwrap.dedent("""\
            * Unmerged path g.txt
            diff --git a/g.txt b/g.txt
            old mode 100755
            new mode 100644
        """)
        assert_stdout(stdout, expected)


class TestConflictedMergeFileDirectoryAddition:
    @pytest.fixture(autouse=True)
    def setup(self, merge3):
        self.cmd, self.stdin, self.stdout, self.stderr = merge3(
            {"f.txt": "1"},
            {"g.txt": "2"},
            {"g.txt/nested.txt": "3"},
        )

    def test_it_prints_the_merge_conflicts(self):
        expected = textwrap.dedent("""\
            Adding g.txt/nested.txt
            CONFLICT (file/directory): There is a directory with name g.txt in topic. Adding g.txt as g.txt~HEAD
            Automatic merge failed; fix conflicts and then commit the result.
        """)
        assert_stdout(self.stdout, expected)

    def test_it_puts_a_namespaced_copy_in_the_workspace(self, repo_path):
        assert_workspace(
            repo_path,
            {
                "f.txt": "1",
                "g.txt~HEAD": "2",
                "g.txt/nested.txt": "3",
            },
        )

    def test_it_records_the_conflict_in_the_index(self, repo):
        assert_index(
            repo,
            ("f.txt", 0),
            ("g.txt", 2),
            ("g.txt/nested.txt", 0),
        )

    def test_it_does_not_write_a_merge_commit(self, load_commit):
        assert_no_merge(load_commit)

    def test_it_reports_the_conflict_in_the_status(self, legit_cmd):
        *_, stdout, _ = legit_cmd("status", "--porcelain")
        expected = textwrap.dedent("""\
            AU g.txt
            A  g.txt/nested.txt
            ?? g.txt~HEAD
        """)
        assert_stdout(stdout, expected)

    def test_it_lists_the_file_as_unmerged_in_the_diff(self, legit_cmd):
        *_, stdout, _ = legit_cmd("diff")
        assert_stdout(stdout, "* Unmerged path g.txt\n")


class TestConflictedMergeDirectoryFileAddition:
    @pytest.fixture(autouse=True)
    def setup(self, merge3):
        self.cmd, self.stdin, self.stdout, self.stderr = merge3(
            {"f.txt": "1"},
            {"g.txt/nested.txt": "2"},
            {"g.txt": "3"},
        )

    def test_it_prints_the_merge_conflicts_directory_file(self):
        expected = textwrap.dedent("""\
            Adding g.txt/nested.txt
            CONFLICT (directory/file): There is a directory with name g.txt in HEAD. Adding g.txt as g.txt~topic
            Automatic merge failed; fix conflicts and then commit the result.
        """)
        assert_stdout(self.stdout, expected)

    def test_it_puts_a_namespaced_copy_in_the_workspace(self, repo_path):
        assert_workspace(
            repo_path,
            {
                "f.txt": "1",
                "g.txt~topic": "3",
                "g.txt/nested.txt": "2",
            },
        )

    def test_it_records_the_conflict_in_the_index(self, repo):
        assert_index(
            repo,
            ("f.txt", 0),
            ("g.txt", 3),
            ("g.txt/nested.txt", 0),
        )

    def test_it_does_not_write_a_merge_commit(self, load_commit):
        assert_no_merge(load_commit)

    def test_it_reports_the_conflict_in_the_status(self, legit_cmd):
        *_, stdout, _ = legit_cmd("status", "--porcelain")
        expected = textwrap.dedent("""\
            UA g.txt
            ?? g.txt~topic
        """)
        assert_stdout(stdout, expected)

    def test_it_lists_the_file_as_unmerged_in_the_diff(self, legit_cmd):
        *_, stdout, _ = legit_cmd("diff")
        assert_stdout(stdout, "* Unmerged path g.txt\n")


class TestConflictedMergeEditEdit:
    @pytest.fixture(autouse=True)
    def setup(self, merge3):
        self.cmd, self.stdin, self.stdout, self.stderr = merge3(
            {"f.txt": "1\n"},
            {"f.txt": "2\n"},
            {"f.txt": "3\n"},
        )

    def test_it_prints_the_merge_conflicts(self):
        expected = textwrap.dedent("""\
            Auto-merging f.txt
            CONFLICT (content): Merge conflict in f.txt
            Automatic merge failed; fix conflicts and then commit the result.
        """)
        assert_stdout(self.stdout, expected)

    def test_it_puts_the_conflicted_file_in_the_workspace(self, repo_path):
        assert_workspace(
            repo_path,
            {
                "f.txt": "<<<<<<< HEAD\n2\n=======\n3\n>>>>>>> topic\n",
            },
        )

    def test_it_records_the_conflict_in_the_index(self, repo):
        assert_index(
            repo,
            ("f.txt", 1),
            ("f.txt", 2),
            ("f.txt", 3),
        )

    def test_it_does_not_write_a_merge_commit(self, load_commit):
        assert_no_merge(load_commit)

    def test_it_reports_the_conflict_in_the_status(self, legit_cmd):
        *_, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "UU f.txt\n")

    def test_shows_combined_diff_against_stages_2_and_3(self, legit_cmd):
        *_, stdout, _ = legit_cmd("diff")

        expected = (
            "diff --cc f.txt\n"
            "index 0cfbf08,00750ed..2603ab2\n"
            "--- a/f.txt\n"
            "+++ b/f.txt\n"
            "@@@ -1,1 -1,1 +1,5 @@@\n"
            "++<<<<<<< HEAD\n"
            " +2\n"
            "++=======\n"
            "+ 3\n"
            "++>>>>>>> topic\n"
        )

        assert_stdout(stdout, expected)


class TestConflictedMergeEditDelete:
    @pytest.fixture(autouse=True)
    def setup(self, merge3):
        self.cmd, self.stdin, self.stdout, self.stderr = merge3(
            {"f.txt": "1"},
            {"f.txt": "2"},
            {"f.txt": None},
        )

    def test_it_prints_the_merge_conflicts(self):
        expected = textwrap.dedent("""\
            CONFLICT (modify/delete): f.txt deleted in topic and modified in HEAD. Version HEAD of f.txt left in tree.
            Automatic merge failed; fix conflicts and then commit the result.
        """)
        assert_stdout(self.stdout, expected)

    def test_it_puts_the_left_version_in_the_workspace(self, repo_path):
        assert_workspace(repo_path, {"f.txt": "2"})

    def test_it_records_the_conflict_in_the_index(self, repo):
        assert_index(
            repo,
            ("f.txt", 1),
            ("f.txt", 2),
        )

    def test_it_does_not_write_a_merge_commit(self, load_commit):
        assert_no_merge(load_commit)

    def test_it_reports_the_conflict_in_the_status(self, legit_cmd):
        *_, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "UD f.txt\n")

    def test_it_lists_the_file_as_unmerged_in_the_diff(self, legit_cmd):
        *_, stdout, _ = legit_cmd("diff")
        assert_stdout(stdout, "* Unmerged path f.txt\n")


class TestConflictedMergeDeleteEdit:
    @pytest.fixture(autouse=True)
    def setup(self, merge3):
        self.cmd, self.stdin, self.stdout, self.stderr = merge3(
            {"f.txt": "1"},
            {"f.txt": None},
            {"f.txt": "3"},
        )

    def test_it_prints_the_merge_conflicts(self):
        expected = textwrap.dedent("""\
            CONFLICT (modify/delete): f.txt deleted in HEAD and modified in topic. Version topic of f.txt left in tree.
            Automatic merge failed; fix conflicts and then commit the result.
        """)
        assert_stdout(self.stdout, expected)

    def test_it_puts_the_right_version_in_the_workspace(self, repo_path):
        assert_workspace(repo_path, {"f.txt": "3"})

    def test_it_records_the_conflict_in_the_index(self, repo):
        assert_index(
            repo,
            ("f.txt", 1),
            ("f.txt", 3),
        )

    def test_it_does_not_write_a_merge_commit(self, load_commit):
        assert_no_merge(load_commit)

    def test_it_reports_the_conflict_in_the_status(self, legit_cmd):
        *_, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "DU f.txt\n")

    def test_it_lists_the_file_as_unmerged_in_the_diff(self, legit_cmd):
        *_, stdout, _ = legit_cmd("diff")
        assert_stdout(stdout, "* Unmerged path f.txt\n")


class TestConflictedMergeEditAddParent:
    @pytest.fixture(autouse=True)
    def setup(self, merge3):
        self.cmd, self.stdin, self.stdout, self.stderr = merge3(
            {"nest/f.txt": "1"},
            {"nest/f.txt": "2"},
            {"nest": "3"},
        )

    def test_it_prints_the_merge_conflicts(self):
        expected = textwrap.dedent("""\
            CONFLICT (modify/delete): nest/f.txt deleted in topic and modified in HEAD. Version HEAD of nest/f.txt left in tree.
            CONFLICT (directory/file): There is a directory with name nest in HEAD. Adding nest as nest~topic
            Automatic merge failed; fix conflicts and then commit the result.
        """)
        assert_stdout(self.stdout, expected)

    def test_it_puts_a_namespaced_copy_in_the_workspace(self, repo_path):
        assert_workspace(
            repo_path,
            {
                "nest/f.txt": "2",
                "nest~topic": "3",
            },
        )

    def test_it_records_the_conflict_in_the_index(self, repo):
        assert_index(
            repo,
            ("nest", 3),
            ("nest/f.txt", 1),
            ("nest/f.txt", 2),
        )

    def test_it_does_not_write_a_merge_commit(self, load_commit):
        assert_no_merge(load_commit)

    def test_it_reports_the_conflict_in_the_status(self, legit_cmd):
        *_, stdout, _ = legit_cmd("status", "--porcelain")
        expected = textwrap.dedent("""\
            UA nest
            UD nest/f.txt
            ?? nest~topic
        """)
        assert_stdout(stdout, expected)

    def test_it_lists_the_file_as_unmerged_in_the_diff(self, legit_cmd):
        *_, stdout, _ = legit_cmd("diff")
        expected = textwrap.dedent("""\
            * Unmerged path nest
            * Unmerged path nest/f.txt
        """)
        assert_stdout(stdout, expected)


class TestConflictedMergeEditAddChild:
    @pytest.fixture(autouse=True)
    def setup(self, merge3):
        self.cmd, self.stdin, self.stdout, self.stderr = merge3(
            {"nest/f.txt": "1"},
            {"nest/f.txt": "2"},
            {"nest/f.txt": None, "nest/f.txt/g.txt": "3"},
        )

    def test_it_prints_the_merge_conflicts(self):
        expected = textwrap.dedent("""\
            Adding nest/f.txt/g.txt
            CONFLICT (modify/delete): nest/f.txt deleted in topic and modified in HEAD. Version HEAD of nest/f.txt left in tree at nest/f.txt~HEAD.
            Automatic merge failed; fix conflicts and then commit the result.
        """)
        assert_stdout(self.stdout, expected)

    def test_it_puts_a_namespaced_copy_in_the_workspace(self, repo_path):
        assert_workspace(
            repo_path,
            {
                "nest/f.txt~HEAD": "2",
                "nest/f.txt/g.txt": "3",
            },
        )

    def test_it_records_the_conflict_in_the_index(self, repo):
        assert_index(
            repo,
            ("nest/f.txt", 1),
            ("nest/f.txt", 2),
            ("nest/f.txt/g.txt", 0),
        )

    def test_it_does_not_write_a_merge_commit(self, load_commit):
        assert_no_merge(load_commit)

    def test_it_reports_the_conflict_in_the_status(self, legit_cmd):
        *_, stdout, _ = legit_cmd("status", "--porcelain")
        expected = textwrap.dedent("""\
            UD nest/f.txt
            A  nest/f.txt/g.txt
            ?? nest/f.txt~HEAD
        """)
        assert_stdout(stdout, expected)

    def test_it_lists_the_file_as_unmerged_in_the_diff(self, legit_cmd):
        *_, stdout, _ = legit_cmd("diff")
        assert_stdout(stdout, "* Unmerged path nest/f.txt\n")


class TestMultipleCommonAncestors:
    @pytest.fixture(autouse=True)
    def setup(self, commit_tree, legit_cmd):
        commit_tree("A", {"f.txt": "1"})
        commit_tree("B", {"f.txt": "2"})
        commit_tree("C", {"f.txt": "3"})

        _ = legit_cmd("branch", "topic", "master^")
        _ = legit_cmd("checkout", "topic")
        commit_tree("D", {"g.txt": "1"})
        commit_tree("E", {"g.txt": "2"})
        commit_tree("F", {"g.txt": "3"})

        _ = legit_cmd("branch", "joiner", "topic^")
        _ = legit_cmd("checkout", "joiner")
        commit_tree("G", {"h.txt": "1"})

        legit_cmd("checkout", "master")

    def test_it_performs_the_first_merge(self, legit_cmd, repo_path):
        cmd, *_ = legit_cmd("merge", "joiner", "-m", "merge joiner")
        assert cmd.status == 0

        assert_workspace(
            repo_path,
            {
                "f.txt": "3",
                "g.txt": "2",
                "h.txt": "1",
            },
        )

        *_, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "")

    def test_it_performs_the_second_merge(self, legit_cmd, commit_tree, repo_path):
        _ = legit_cmd("merge", "joiner", "-m", "merge joiner")

        commit_tree("H", {"f.txt": "4"})

        cmd, *_ = legit_cmd("merge", "topic", "-m", "merge topic")
        assert cmd.status == 0

        assert_workspace(
            repo_path,
            {
                "f.txt": "4",
                "g.txt": "3",
                "h.txt": "1",
            },
        )

        *_, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "")


class TestConflictResolution:
    @pytest.fixture(autouse=True)
    def setup(self, merge3):
        merge3({"f.txt": "1\n"}, {"f.txt": "2\n"}, {"f.txt": "3\n"})

    def test_prevents_commits_with_unmerged_entries(self, legit_cmd, load_commit):
        cmd, *_, stderr = legit_cmd("commit")
        assert cmd.status == 128
        expected = (
            "error: Committing is not possible because you have unmerged files.\n"
            "hint: Fix them up in the work tree, and then use 'legit add/rm <file>'\n"
            "hint: as appropriate to mark resolution and make a commit.\n"
            "fatal: Exiting because of an unresolved conflict.\n"
        )
        assert_stderr(stderr, expected)
        assert load_commit("@").message.strip() == "B"

    def test_prevents_merge_continue_with_unmerged_entries(
        self, legit_cmd, load_commit
    ):
        cmd, *_, stderr = legit_cmd("merge", "--continue")
        assert cmd.status == 128
        expected = (
            "error: Committing is not possible because you have unmerged files.\n"
            "hint: Fix them up in the work tree, and then use 'legit add/rm <file>'\n"
            "hint: as appropriate to mark resolution and make a commit.\n"
            "fatal: Exiting because of an unresolved conflict.\n"
        )
        assert_stderr(stderr, expected)
        assert load_commit("@").message.strip() == "B"

    def test_commits_a_merge_after_resolving_conflicts(self, legit_cmd, load_commit):
        _ = legit_cmd("add", "f.txt")
        cmd, *_ = legit_cmd("commit")
        assert cmd.status == 0
        commit = load_commit("@")
        assert commit.message.strip() == "M"
        parents = [load_commit(oid).message.strip() for oid in commit.parents]
        assert parents == ["B", "C"]

    def test_allows_merge_continue_after_resolving_conflicts(
        self, legit_cmd, load_commit
    ):
        _ = legit_cmd("add", "f.txt")
        cmd, _, _, _ = legit_cmd("merge", "--continue")
        assert cmd.status == 0
        commit = load_commit("@")
        assert commit.message.strip() == "M"
        parents = [load_commit(oid).message.strip() for oid in commit.parents]
        assert parents == ["B", "C"]

    def test_prevents_merge_continue_when_none_in_progress(self, legit_cmd):
        _ = legit_cmd("add", "f.txt")
        _ = legit_cmd("merge", "--continue")
        cmd, *_, stderr = legit_cmd("merge", "--continue")
        assert cmd.status == 128
        assert_stderr(
            stderr, "fatal: There is no merge in progress (MERGE_HEAD missing).\n"
        )

    def test_aborts_the_merge(self, legit_cmd):
        cmd, *_ = legit_cmd("merge", "--abort")
        assert cmd.status == 0
        *_, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "")

    def test_prevents_aborting_merge_when_none_in_progress(self, legit_cmd):
        legit_cmd("merge", "--abort")
        cmd, *_, stderr = legit_cmd("merge", "--abort")
        assert cmd.status == 128
        assert_stderr(
            stderr, "fatal: There is no merge to abort (MERGE_HEAD missing).\n"
        )

    def test_prevents_starting_new_merge_while_one_in_progress(self, legit_cmd):
        cmd, *_, stderr = legit_cmd("merge")
        assert cmd.status == 128
        expected = (
            "error: Merging is not possible because you have unmerged files.\n"
            "hint: Fix them up in the work tree, and then use 'legit add/rm <file>'\n"
            "hint: as appropriate to mark resolution and make a commit.\n"
            "fatal: Exiting because of an unresolved conflict.\n"
        )
        assert_stderr(stderr, expected)
