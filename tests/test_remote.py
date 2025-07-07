import pytest

from tests.cmd_helpers import (
    assert_status,
    assert_stdout,
    assert_stderr,
)


class TestAddingRemote:
    @pytest.fixture(autouse=True)
    def add_origin(self, legit_cmd):
        cmd, *_ = legit_cmd("remote", "add", "origin", "ssh://example.com/repo")
        assert_status(cmd, 0)

    def test_it_fails_to_add_an_existing_remote(self, legit_cmd):
        cmd, _, _, stderr = legit_cmd("remote", "add", "origin", "url")
        assert_status(cmd, 128)
        assert_stderr(stderr, "fatal: remote origin already exists.\n")

    def test_it_lists_the_remote(self, legit_cmd):
        cmd, _, stdout, _ = legit_cmd("remote")
        assert_status(cmd, 0)
        assert_stdout(stdout, "origin\n")

    def test_it_lists_the_remote_with_urls(self, legit_cmd):
        cmd, _, stdout, _ = legit_cmd("remote", "--verbose")
        expected = (
            "origin\tssh://example.com/repo (fetch)\n"
            "origin\tssh://example.com/repo (push)\n"
        )
        assert_status(cmd, 0)
        assert_stdout(stdout, expected)

    def test_it_sets_a_catch_all_fetch_refspec(self, legit_cmd):
        cmd, _, stdout, _ = legit_cmd(
            "config", "--local", "--get-all", "remote.origin.fetch"
        )
        expected = "+refs/heads/*:refs/remotes/origin/*\n"
        assert_status(cmd, 0)
        assert_stdout(stdout, expected)


class TestAddingRemoteWithTrackingBranches:
    @pytest.fixture(autouse=True)
    def add_origin_with_tracking(self, legit_cmd):
        cmd, _, _, _ = legit_cmd(
            "remote", "add", "origin", "ssh://example.com/repo",
            "-t", "master", "-t", "topic"
        )
        assert cmd.status == 0

    def test_it_sets_fetch_refspec_for_each_branch(self, legit_cmd):
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
        cmd, *_ = legit_cmd("remote", "add", "origin", "ssh://example.com/repo")
        assert cmd.status == 0

    def test_it_removes_the_remote(self, legit_cmd):
        cmd, *_ = legit_cmd("remote", "remove", "origin")
        assert_status(cmd, 0)
        cmd2, _, stdout, _ = legit_cmd("remote")
        assert_status(cmd2, 0)
        assert_stdout(stdout, "")

    def test_it_fails_to_remove_missing_remote(self, legit_cmd):
        cmd, _, _, stderr = legit_cmd("remote", "remove", "no-such")
        assert_status(cmd, 128)
        assert_stderr(stderr, "fatal: No such remote: no-such\n")

