from pathlib import Path

import pytest

from tests.cmd_helpers import (
    assert_status,
    assert_stderr,
    assert_workspace,
)


class TestWithASingleFile:
    @pytest.fixture(autouse=True)
    def setup(self, write_file, legit_cmd, commit):
        write_file("f.txt", "1")
        legit_cmd("add", ".")
        commit("first")

    def test_it_exits_successfully(self, legit_cmd):
        cmd, *_ = legit_cmd("rm", "f.txt")
        assert_status(cmd, 0)

    def test_it_removes_a_file_from_the_index(self, legit_cmd, repo):
        legit_cmd("rm", "f.txt")
        
        repo.index.load()
        assert not repo.index.is_tracked_file(Path("f.txt"))

    def test_it_removes_a_file_from_the_workspace(self, legit_cmd, repo_path):
        legit_cmd("rm", "f.txt")
        assert_workspace(repo_path, {})

    def test_it_succeeds_if_the_file_is_not_in_the_workspace(self, delete, legit_cmd, repo):
        delete("f.txt")
        cmd, *_ = legit_cmd("rm", "f.txt")

        assert_status(cmd, 0)
        
        repo.index.load()
        assert not repo.index.is_tracked_file(Path("f.txt"))

    def test_it_fails_if_the_file_is_not_in_the_index(self, legit_cmd):
        cmd, *_, stderr = legit_cmd("rm", "nope.txt")
        assert_status(cmd, 128)
        assert_stderr(stderr, "fatal: pathspec 'nope.txt' did not match any files\n")

    def test_it_fails_if_the_file_has_unstaged_changes(self, write_file, legit_cmd, repo, repo_path):
        write_file("f.txt", "2")
        cmd, *_, stderr = legit_cmd("rm", "f.txt")

        assert_stderr(stderr, (
            "error: the following file has local modifications:\n"
            "    f.txt\n"
        )) 

        assert_status(cmd, 1)
        
        repo.index.load()
        assert repo.index.is_tracked_file(Path("f.txt"))
        assert_workspace(repo_path, {"f.txt": "2"})

    def test_it_fails_if_the_file_has_uncommitted_changes(self, write_file, legit_cmd, repo, repo_path):
        write_file("f.txt", "2")
        _ = legit_cmd("add", "f.txt")

        cmd, *_, stderr = legit_cmd("rm", "f.txt")

        assert_stderr(stderr, (
            "error: the following file has changes staged in the index:\n"
            "    f.txt\n"
        ))
        
        assert_status(cmd, 1)

        repo.index.load()
        assert repo.index.is_tracked_file(Path("f.txt"))
        assert_workspace(repo_path, {"f.txt": "2"})

    def test_it_forces_removal_of_unstaged_changes(self, write_file, legit_cmd, repo, repo_path):
        write_file("f.txt", "2")
        legit_cmd("rm", "-f", "f.txt")

        repo.index.load()
        assert not repo.index.is_tracked_file(Path("f.txt"))
        assert_workspace(repo_path, {})

    def test_it_forces_removal_of_uncommitted_changes(self, write_file, legit_cmd, repo, repo_path):
        write_file("f.txt", "2")
        legit_cmd("add", "f.txt")
        legit_cmd("rm", "-f", "f.txt")
        
        repo.index.load()
        assert not repo.index.is_tracked_file(Path("f.txt"))
        assert_workspace(repo_path, {})

    def test_it_removes_a_file_from_the_index_if_it_has_unstaged_changes(self, legit_cmd, repo, repo_path):
        legit_cmd("rm", "--cached", "f.txt")

        repo.index.load()
        assert not repo.index.is_tracked_file(Path("f.txt"))
        assert_workspace(repo_path, {"f.txt": "1"})

    def test_it_removes_a_file_from_the_index_if_it_has_uncommited_changes(self, write_file, legit_cmd, repo, repo_path):
        write_file("f.txt", "2")
        legit_cmd("rm", "--cached", "f.txt")
        repo.index.load()
        assert not repo.index.is_tracked_file(Path("f.txt"))
        assert_workspace(repo_path, {"f.txt": "2"})

    def test_it_does_not_remove_a_file_with_both_unstaged_and_uncommitted_changes(self, write_file, legit_cmd, repo, repo_path):
        write_file("f.txt", "2")
        legit_cmd("add", "f.txt")
        write_file("f.txt", "3")
        
        cmd, *_, stderr = legit_cmd("rm", "--cached", "f.txt")
        assert_status(cmd, 1)
        
        assert_stderr(stderr, (
            "error: the following file has staged content different from both the file and the HEAD:\n"
            "    f.txt\n"
        ))
        
        repo.index.load()
        assert repo.index.is_tracked_file(Path("f.txt"))
        assert_workspace(repo_path, {"f.txt": "3"})


class TestRmTree:
    @pytest.fixture(autouse=True)
    def setup(self, write_file, legit_cmd, commit):
        write_file("f.txt", "1")
        write_file("outer/g.txt", "2")
        write_file("outer/inner/h.txt", "3")
        _ = legit_cmd("add", ".")
        commit("first")

    def test_it_removes_multiple_files(self, legit_cmd, repo, repo_path):
        legit_cmd("rm", "f.txt", "outer/inner/h.txt")

        repo.index.load()
        paths = [str(e.path) for _, e in repo.index.entries.items()]
        assert paths == ["outer/g.txt"]
        assert_workspace(repo_path, {"outer/g.txt": "2"})

    def test_it_refuses_to_remove_a_directory(self, legit_cmd, repo, repo_path):
        cmd, *_, stderr = legit_cmd("rm", "f.txt", "outer")

        assert_status(cmd, 128)
        assert_stderr(stderr, "fatal: not removing 'outer' recursively without -r\n")
        
        repo.index.load()
        paths = [str(e.path) for _, e in repo.index.entries.items()]
        assert set(paths) == {"f.txt", "outer/g.txt", "outer/inner/h.txt"}
        assert_workspace(repo_path, {
            "f.txt": "1",
            "outer/g.txt": "2",
            "outer/inner/h.txt": "3"
        })

    def test_it_does_not_remove_a_file_replaced_with_directory(self, delete, write_file, legit_cmd, repo, repo_path):
        delete("f.txt")
        write_file("f.txt/nested", "keep me")
        
        cmd, *_, stderr = legit_cmd("rm", "f.txt")
        
        assert_status(cmd, 128)
        assert_stderr(stderr, "fatal: legit rm: 'f.txt': Operation not permitted\n")
        
        repo.index.load()
        paths = [str(e.path) for _, e in repo.index.entries.items()]
        assert set(paths) == {"f.txt", "outer/g.txt", "outer/inner/h.txt"}
        assert_workspace(repo_path, {
            "f.txt/nested": "keep me",
            "outer/g.txt": "2",
            "outer/inner/h.txt": "3"
        })

    def test_it_removes_directory_with_recursive_flag(self, legit_cmd, repo, repo_path):
        legit_cmd("rm", "-r", "outer")
        
        repo.index.load()
        paths = [str(e.path) for _, e in repo.index.entries.items()]
        assert paths == ["f.txt"]
        assert_workspace(repo_path, {"f.txt": "1"})

    def test_it_does_not_remove_untracked_files(self, write_file, legit_cmd, repo, repo_path):
        write_file("outer/inner/j.txt", "4")
        legit_cmd("rm", "-r", "outer")
        
        repo.index.load()
        paths = [str(e.path) for _, e in repo.index.entries.items()]
        assert paths == ["f.txt"]
        assert_workspace(repo_path, {
            "f.txt": "1",
            "outer/inner/j.txt": "4"
        })

