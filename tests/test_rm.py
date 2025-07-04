from pathlib import Path
import pytest
from tests.conftest import assert_stderr


def _snapshot_workspace(repo_path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in repo_path.rglob("*"):
        if ".git" in path.parts or not path.is_file():
            continue
        result[str(path.relative_to(repo_path))] = path.read_text()
    return result


def assert_workspace(repo_path: Path, expected: dict[str, str]):
    actual = _snapshot_workspace(repo_path)
    assert actual == expected, f"workspace mismatch – expected {expected}, got {actual}"


class TestRmSingleFile:
    @pytest.fixture(autouse=True)
    def setup(self, write_file, legit_cmd, commit):
        # Initialize repository with one tracked file
        write_file("f.txt", "1")
        legit_cmd("add", ".")
        commit("first")

    def test_exits_successfully(self, legit_cmd):
        cmd, _, _, _ = legit_cmd("rm", "f.txt")
        assert cmd.status == 0

    def test_removes_file_from_index(self, legit_cmd, repo):
        legit_cmd("rm", "f.txt")
        repo.index.load()
        assert not repo.index.is_tracked_file(Path("f.txt"))

    def test_removes_file_from_workspace(self, legit_cmd, repo_path):
        legit_cmd("rm", "f.txt")
        assert_workspace(repo_path, {})

    def test_succeeds_if_file_not_in_workspace(self, delete, legit_cmd, repo):
        delete("f.txt")
        cmd, _, _, _ = legit_cmd("rm", "f.txt")
        assert cmd.status == 0
        repo.index.load()
        assert not repo.index.is_tracked_file(Path("f.txt"))

    def test_fails_if_file_not_in_index(self, legit_cmd):
        cmd, _, _, stderr = legit_cmd("rm", "nope.txt")
        assert cmd.status == 128
        assert_stderr(stderr, "fatal: pathspec 'nope.txt' did not match any files\n")

    def test_fails_if_file_has_unstaged_changes(self, write_file, legit_cmd, repo, repo_path):
        write_file("f.txt", "2")
        cmd, _, _, stderr = legit_cmd("rm", "f.txt")
        assert cmd.status == 1
        assert_stderr(stderr, (
            "error: the following file has local modifications:\n"
            "    f.txt\n"
        ))
        repo.index.load()
        assert repo.index.is_tracked_file(Path("f.txt"))
        assert_workspace(repo_path, {"f.txt": "2"})

    def test_fails_if_file_has_uncommitted_changes(self, write_file, legit_cmd, repo, repo_path):
        write_file("f.txt", "2")
        legit_cmd("add", "f.txt")
        cmd, _, _, stderr = legit_cmd("rm", "f.txt")
        assert cmd.status == 1
        assert_stderr(stderr, (
            "error: the following file has changes staged in the index:\n"
            "    f.txt\n"
        ))
        repo.index.load()
        assert repo.index.is_tracked_file(Path("f.txt"))
        assert_workspace(repo_path, {"f.txt": "2"})

    def test_forces_removal_of_unstaged_changes(self, write_file, legit_cmd, repo, repo_path):
        write_file("f.txt", "2")
        legit_cmd("rm", "-f", "f.txt")
        repo.index.load()
        assert not repo.index.is_tracked_file(Path("f.txt"))
        assert_workspace(repo_path, {})

    def test_forces_removal_of_uncommitted_changes(self, write_file, legit_cmd, repo, repo_path):
        write_file("f.txt", "2")
        legit_cmd("add", "f.txt")
        legit_cmd("rm", "-f", "f.txt")
        repo.index.load()
        assert not repo.index.is_tracked_file(Path("f.txt"))
        assert_workspace(repo_path, {})

    def test_removes_file_only_from_index(self, legit_cmd, repo, repo_path):
        legit_cmd("rm", "--cached", "f.txt")
        repo.index.load()
        assert not repo.index.is_tracked_file(Path("f.txt"))
        assert_workspace(repo_path, {"f.txt": "1"})

    def test_removes_index_with_unstaged_changes(self, write_file, legit_cmd, repo, repo_path):
        write_file("f.txt", "2")
        legit_cmd("rm", "--cached", "f.txt")
        repo.index.load()
        assert not repo.index.is_tracked_file(Path("f.txt"))
        assert_workspace(repo_path, {"f.txt": "2"})

    def test_removes_index_with_uncommitted_changes(self, write_file, legit_cmd, repo, repo_path):
        write_file("f.txt", "2")
        legit_cmd("add", "f.txt")
        legit_cmd("rm", "--cached", "f.txt")
        repo.index.load()
        assert not repo.index.is_tracked_file(Path("f.txt"))
        assert_workspace(repo_path, {"f.txt": "2"})

    def test_does_not_remove_with_both_unstaged_and_uncommitted(self, write_file, legit_cmd, repo, repo_path):
        write_file("f.txt", "2")
        legit_cmd("add", "f.txt")
        write_file("f.txt", "3")
        cmd, _, _, stderr = legit_cmd("rm", "--cached", "f.txt")
        assert cmd.status == 1
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
        legit_cmd("add", ".")
        commit("first")

    def test_removes_multiple_files(self, legit_cmd, repo, repo_path):
        legit_cmd("rm", "f.txt", "outer/inner/h.txt")
        repo.index.load()
        paths = [str(e.path) for _, e in repo.index.entries.items()]
        assert paths == ["outer/g.txt"]
        assert_workspace(repo_path, {"outer/g.txt": "2"})

    def test_refuses_to_remove_directory(self, legit_cmd, repo, repo_path):
        cmd, _, _, stderr = legit_cmd("rm", "f.txt", "outer")
        assert cmd.status == 128
        assert_stderr(stderr, "fatal: not removing 'outer' recursively without -r\n")
        repo.index.load()
        paths = [str(e.path) for _, e in repo.index.entries.items()]
        assert set(paths) == {"f.txt", "outer/g.txt", "outer/inner/h.txt"}
        assert_workspace(repo_path, {
            "f.txt": "1",
            "outer/g.txt": "2",
            "outer/inner/h.txt": "3"
        })

    def test_does_not_remove_replaced_with_directory(self, delete, write_file, legit_cmd, repo, repo_path):
        delete("f.txt")
        write_file("f.txt/nested", "keep me")
        cmd, _, _, stderr = legit_cmd("rm", "f.txt")
        assert cmd.status == 128
        assert_stderr(stderr, "fatal: legit rm: 'f.txt': Operation not permitted\n")
        repo.index.load()
        paths = [str(e.path) for _, e in repo.index.entries.items()]
        assert set(paths) == {"f.txt", "outer/g.txt", "outer/inner/h.txt"}
        assert_workspace(repo_path, {
            "f.txt/nested": "keep me",
            "outer/g.txt": "2",
            "outer/inner/h.txt": "3"
        })

    def test_removes_directory_with_recursive_flag(self, legit_cmd, repo, repo_path):
        legit_cmd("rm", "-r", "outer")
        repo.index.load()
        paths = [str(e.path) for _, e in repo.index.entries.items()]
        assert paths == ["f.txt"]
        assert_workspace(repo_path, {"f.txt": "1"})

    def test_does_not_remove_untracked_files(self, write_file, legit_cmd, repo, repo_path):
        write_file("outer/inner/j.txt", "4")
        legit_cmd("rm", "-r", "outer")
        repo.index.load()
        paths = [str(e.path) for _, e in repo.index.entries.items()]
        assert paths == ["f.txt"]
        assert_workspace(repo_path, {
            "f.txt": "1",
            "outer/inner/j.txt": "4"
        })

