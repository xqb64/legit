import pytest

from tests.conftest import assert_status, assert_stdout, assert_stderr


class TestAddingRemote:
    @pytest.fixture(autouse=True)
    def add_origin(self, legit_cmd):
        # Add a remote before each test
        cmd, _, _, _ = legit_cmd("remote", "add", "origin", "ssh://example.com/repo")
        assert cmd.status == 0

    def test_fails_to_add_existing_remote(self, legit_cmd):
        cmd, _, _, stderr = legit_cmd("remote", "add", "origin", "url")
        # Should error because 'origin' already exists
        assert_status(cmd, 128)
        assert_stderr(stderr, "fatal: remote origin already exists.\n")

    def test_lists_remote(self, legit_cmd):
        cmd, _, stdout, _ = legit_cmd("remote")
        # Should list the remote name
        assert_status(cmd, 0)
        assert_stdout(stdout, "origin\n")

    def test_lists_remote_with_urls(self, legit_cmd):
        cmd, _, stdout, _ = legit_cmd("remote", "--verbose")
        expected = (
            "origin\tssh://example.com/repo (fetch)\n"
            "origin\tssh://example.com/repo (push)\n"
        )
        assert_status(cmd, 0)
        assert_stdout(stdout, expected)

    def test_sets_catch_all_fetch_refspec(self, legit_cmd):
        cmd, _, stdout, _ = legit_cmd(
            "config", "--local", "--get-all", "remote.origin.fetch"
        )
        expected = "+refs/heads/*:refs/remotes/origin/*\n"
        assert_status(cmd, 0)
        assert_stdout(stdout, expected)


class TestAddingRemoteWithTrackingBranches:
    @pytest.fixture(autouse=True)
    def add_origin_with_tracking(self, legit_cmd):
        # Add a remote with -t master and -t topic
        cmd, _, _, _ = legit_cmd(
            "remote", "add", "origin", "ssh://example.com/repo",
            "-t", "master", "-t", "topic"
        )
        assert cmd.status == 0

    def test_sets_fetch_refspec_for_each_branch(self, legit_cmd):
        cmd, _, stdout, _ = legit_cmd(
            "config", "--local", "--get-all", "remote.origin.fetch"
        )
        expected = (
            "+refs/heads/master:refs/remotes/origin/master\n"
            "+refs/heads/topic:refs/remotes/origin/topic\n"
        )
        assert_status(cmd, 0)
        assert_stdout(stdout, expected)


class TestRemovingRemote:
    @pytest.fixture(autouse=True)
    def add_origin(self, legit_cmd):
        # Ensure a remote exists before tests
        cmd, _, _, _ = legit_cmd("remote", "add", "origin", "ssh://example.com/repo")
        assert cmd.status == 0

    def test_removes_remote(self, legit_cmd):
        cmd, _, _, _ = legit_cmd("remote", "remove", "origin")
        assert_status(cmd, 0)
        # After removal, listing should be empty
        cmd2, _, stdout, _ = legit_cmd("remote")
        assert_status(cmd2, 0)
        assert_stdout(stdout, "")

    def test_fails_to_remove_missing_remote(self, legit_cmd):
        cmd, _, _, stderr = legit_cmd("remote", "remove", "no-such")
        assert_status(cmd, 128)
        assert_stderr(stderr, "fatal: No such remote: no-such\n")

