import textwrap

import pytest

from tests.cmd_helpers import (
    assert_stdout,
)


def assert_status(legit_cmd, output):
    *_, stdout, _ = legit_cmd("status", "--porcelain")
    assert_stdout(stdout, output)


def test_it_lists_files_as_untracked_if_they_are_not_in_the_index(
    write_file, commit, legit_cmd
):
    write_file("committed.txt", "")
    legit_cmd("add", ".")
    commit("commit message")

    write_file("file.txt", "")

    expected = textwrap.dedent(
        """\
        ?? file.txt
        """
    )

    assert_status(legit_cmd, expected)


def test_it_lists_untracked_files_in_name_order(write_file, legit_cmd):
    write_file("file.txt", "")
    write_file("another.txt", "")

    expected = textwrap.dedent(
        """\
        ?? another.txt
        ?? file.txt
        """
    )

    assert_status(legit_cmd, expected)


def test_it_lists_untracked_directories_and_not_their_contents(write_file, legit_cmd):
    write_file("file.txt", "")
    write_file("dir/another.txt", "")

    expected = textwrap.dedent(
        """\
        ?? dir/
        ?? file.txt
        """
    )

    assert_status(legit_cmd, expected)


def test_it_lists_untracked_files_inside_tracked_directories(
    write_file, commit, legit_cmd
):
    write_file("a/b/inner.txt", "")
    legit_cmd("add", ".")
    commit("commit message")

    write_file("a/outer.txt", "")
    write_file("a/b/c/file.txt", "")

    expected = textwrap.dedent(
        """\
        ?? a/b/c/
        ?? a/outer.txt
        """
    )

    assert_status(legit_cmd, expected)


def test_it_does_not_list_empty_untracked_directories(mkdir, legit_cmd):
    mkdir("outer")
    expected = ""

    assert_status(legit_cmd, expected)


def test_it_lists_untracked_directories_that_indirectly_contain_files(
    write_file, legit_cmd
):
    write_file("outer/inner/file.txt", "")

    expected = textwrap.dedent(
        """\
        ?? outer/
        """
    )

    assert_status(legit_cmd, expected)


class TestIndexWorkspaceChanges:
    @pytest.fixture(autouse=True)
    def setup(self, write_file, legit_cmd, commit):
        write_file("1.txt", "one")
        write_file("a/2.txt", "two")
        write_file("a/b/3.txt", "three")

        _ = legit_cmd("add", ".")
        commit("commit message")

    def test_it_no_changes_prints_nothing(self, legit_cmd):
        assert_status(legit_cmd, "")

    def test_it_reports_modified_files(self, write_file, legit_cmd):
        write_file("1.txt", "changed")
        write_file("a/2.txt", "modified")
        assert_status(legit_cmd, " M 1.txt\n M a/2.txt\n")

    def test_it_reports_changed_mode(self, make_executable, legit_cmd):
        make_executable("a/2.txt")
        assert_status(legit_cmd, " M a/2.txt\n")

    def test_it_reports_modified_files_with_unchanged_size(self, write_file, legit_cmd):
        write_file("a/b/3.txt", "hello")
        assert_status(legit_cmd, " M a/b/3.txt\n")

    def test_it_prints_nothing_when_file_is_touched(self, touch, legit_cmd):
        touch("1.txt")
        assert_status(legit_cmd, "")

    def test_it_reports_deleted_files(self, delete, legit_cmd):
        delete("a/2.txt")
        assert_status(legit_cmd, " D a/2.txt\n")


class TestHeadIndexChanges:
    @pytest.fixture(autouse=True)
    def setup(self, write_file, legit_cmd, commit):
        write_file("1.txt", "one")
        write_file("a/2.txt", "two")
        write_file("a/b/3.txt", "three")

        _ = legit_cmd("add", ".")
        commit("commit message")

    def test_it_reports_file_added_to_tracked_directory(self, legit_cmd, write_file):
        write_file("a/4.txt", "four")
        legit_cmd("add", ".")
        assert_status(legit_cmd, "A  a/4.txt\n")

    def test_it_reports_file_added_to_untracked_directory(self, legit_cmd, write_file):
        write_file("d/e/5.txt", "five")
        legit_cmd("add", ".")
        assert_status(legit_cmd, "A  d/e/5.txt\n")

    def test_it_reports_modified_modes(self, legit_cmd, make_executable):
        make_executable("1.txt")
        legit_cmd("add", ".")
        assert_status(legit_cmd, "M  1.txt\n")

    def test_it_reports_modified_contents(self, legit_cmd, write_file):
        write_file("a/b/3.txt", "changed")
        legit_cmd("add", ".")
        assert_status(legit_cmd, "M  a/b/3.txt\n")

    def test_it_reports_deleted_files(self, legit_cmd, delete):
        delete("1.txt")
        delete(".git/index")
        legit_cmd("add", ".")
        assert_status(legit_cmd, "D  1.txt\n")

    def test_it_reports_all_deleted_files_inside_directories(self, legit_cmd, delete):
        delete("a")
        delete(".git/index")
        legit_cmd("add", ".")
        assert_status(legit_cmd, "D  a/2.txt\nD  a/b/3.txt\n")
