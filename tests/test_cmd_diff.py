import pytest

from tests.cmd_helpers import assert_stdout


def assert_diff(legit_cmd, output):
    *_, stdout, _ = legit_cmd("diff")
    assert_stdout(stdout, output)


def assert_diff_cached(legit_cmd, output):
    *_, stdout, _ = legit_cmd("diff", "--cached")
    assert_stdout(stdout, output)


@pytest.mark.usefixtures("setup_and_teardown")
class TestWithFileInIndex:
    @pytest.fixture(autouse=True)
    def setup(self, write_file, legit_cmd):
        write_file("file.txt", "contents\n")
        _ = legit_cmd("add", ".")

    def test_it_diffs_a_file_with_modified_contents(self, legit_cmd, write_file):
        write_file("file.txt", "changed\n")

        expected_diff = (
            "diff --git a/file.txt b/file.txt\n"
            "index 12f00e9..5ea2ed4 100644\n"
            "--- a/file.txt\n"
            "+++ b/file.txt\n"
            "@@ -1,1 +1,1 @@\n"
            "-contents\n"
            "+changed\n"
        )
        assert_diff(legit_cmd, expected_diff)

    def test_it_diffs_a_file_with_changed_mode(self, legit_cmd, make_executable):
        make_executable("file.txt")

        expected_diff = (
            "diff --git a/file.txt b/file.txt\nold mode 100644\nnew mode 100755\n"
        )
        assert_diff(legit_cmd, expected_diff)

    def test_it_diffs_a_file_with_changed_mode_and_contents(
        self, legit_cmd, make_executable, write_file
    ):
        make_executable("file.txt")
        write_file("file.txt", "changed\n")

        expected_diff = (
            "diff --git a/file.txt b/file.txt\n"
            "old mode 100644\n"
            "new mode 100755\n"
            "index 12f00e9..5ea2ed4\n"
            "--- a/file.txt\n"
            "+++ b/file.txt\n"
            "@@ -1,1 +1,1 @@\n"
            "-contents\n"
            "+changed\n"
        )
        assert_diff(legit_cmd, expected_diff)

    def test_it_diffs_a_deleted_file(self, legit_cmd, delete):
        delete("file.txt")

        expected_diff = (
            "diff --git a/file.txt b/file.txt\n"
            "deleted file mode 100644\n"
            "index 12f00e9..0000000\n"
            "--- a/file.txt\n"
            "+++ /dev/null\n"
            "@@ -1,1 +0,0 @@\n"
            "-contents\n"
        )
        assert_diff(legit_cmd, expected_diff)


@pytest.mark.usefixtures("setup_and_teardown")
class TestWithHeadCommit:
    @pytest.fixture(autouse=True)
    def setup(self, write_file, legit_cmd, commit):
        write_file("file.txt", "contents\n")
        legit_cmd("add", ".")
        commit("first commit")

    def test_it_diffs_a_file_with_modified_contents(self, legit_cmd, write_file):
        write_file("file.txt", "changed\n")
        legit_cmd("add", ".")

        expected_diff = (
            "diff --git a/file.txt b/file.txt\n"
            "index 12f00e9..5ea2ed4 100644\n"
            "--- a/file.txt\n"
            "+++ b/file.txt\n"
            "@@ -1,1 +1,1 @@\n"
            "-contents\n"
            "+changed\n"
        )
        assert_diff_cached(legit_cmd, expected_diff)

    def test_it_diffs_a_file_with_changed_mode(self, legit_cmd, make_executable):
        make_executable("file.txt")
        legit_cmd("add", ".")

        expected_diff = (
            "diff --git a/file.txt b/file.txt\nold mode 100644\nnew mode 100755\n"
        )
        assert_diff_cached(legit_cmd, expected_diff)

    def test_it_diffs_a_file_with_changed_mode_and_contents(
        self, legit_cmd, make_executable, write_file
    ):
        make_executable("file.txt")
        write_file("file.txt", "changed\n")
        legit_cmd("add", ".")

        expected_diff = (
            "diff --git a/file.txt b/file.txt\n"
            "old mode 100644\n"
            "new mode 100755\n"
            "index 12f00e9..5ea2ed4\n"
            "--- a/file.txt\n"
            "+++ b/file.txt\n"
            "@@ -1,1 +1,1 @@\n"
            "-contents\n"
            "+changed\n"
        )
        assert_diff_cached(legit_cmd, expected_diff)

    def test_it_diffs_a_deleted_file(self, legit_cmd, delete, repo_path):
        delete("file.txt")
        delete(".git/index")
        legit_cmd("add", ".")

        expected_diff = (
            "diff --git a/file.txt b/file.txt\n"
            "deleted file mode 100644\n"
            "index 12f00e9..0000000\n"
            "--- a/file.txt\n"
            "+++ /dev/null\n"
            "@@ -1,1 +0,0 @@\n"
            "-contents\n"
        )
        assert_diff_cached(legit_cmd, expected_diff)

    def test_it_diffs_an_added_file(self, legit_cmd, write_file):
        write_file("another.txt", "hello\n")
        legit_cmd("add", ".")

        expected_diff = (
            "diff --git a/another.txt b/another.txt\n"
            "new file mode 100644\n"
            "index 0000000..ce01362\n"
            "--- /dev/null\n"
            "+++ b/another.txt\n"
            "@@ -0,0 +1,1 @@\n"
            "+hello\n"
        )
        assert_diff_cached(legit_cmd, expected_diff)
