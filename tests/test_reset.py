from pathlib import Path
import pytest

from tests.conftest import assert_stdout


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


class TestResetNoHead:
    @pytest.fixture(autouse=True)
    def setup(self, write_file, legit_cmd):
        # Prepare working tree and index without any HEAD commit
        write_file("a.txt", "1")
        write_file("outer/b.txt", "2")
        write_file("outer/inner/c.txt", "3")
        legit_cmd("add", ".")

    def assert_index(self, repo, expected):
        files = {}
        repo.index.load()
        for entry in repo.index.entries.values():
            files[str(entry.path)] = repo.database.load(entry.oid).data
        assert files == expected

    def assert_unchanged_workspace(self, repo_path):
        assert_workspace(repo_path, {
            "a.txt": "1",
            "outer/b.txt": "2",
            "outer/inner/c.txt": "3",
        })

    def test_removes_everything_from_index(self, legit_cmd, repo, repo_path):
        legit_cmd("reset")
        # index should be empty, workspace untouched
        self.assert_index(repo, {})
        self.assert_unchanged_workspace(repo_path)

    def test_removes_single_file_from_index(self, legit_cmd, repo, repo_path):
        legit_cmd("reset", "a.txt")
        self.assert_index(repo, {
            "outer/b.txt": "2",
            "outer/inner/c.txt": "3",
        })
        self.assert_unchanged_workspace(repo_path)

    def test_removes_directory_from_index(self, legit_cmd, repo, repo_path):
        legit_cmd("reset", "outer")
        self.assert_index(repo, {"a.txt": "1"})
        self.assert_unchanged_workspace(repo_path)


class TestResetWithHead:
    @pytest.fixture(autouse=True)
    def setup(self, write_file, legit_cmd, commit, repo):
        # Create initial commits
        write_file("a.txt", "1")
        write_file("outer/b.txt", "2")
        write_file("outer/inner/c.txt", "3")
        legit_cmd("add", ".")
        commit("first")

        write_file("outer/b.txt", "4")
        legit_cmd("add", ".")
        commit("second")

        # Stage a removal and new changes without committing
        legit_cmd("rm", "a.txt")
        write_file("outer/d.txt", "5")
        write_file("outer/inner/c.txt", "6")
        legit_cmd("add", ".")
        write_file("outer/e.txt", "7")

        # Record HEAD before reset operations
        self.head_oid = repo.refs.read_head()

    def assert_index(self, repo, expected):
        files = {}
        repo.index.load()
        for entry in repo.index.entries.values():
            files[str(entry.path)] = repo.database.load(entry.oid).data
        assert files == expected

    def assert_unchanged_workspace(self, repo_path):
        assert_workspace(repo_path, {
            "outer/b.txt": "4",
            "outer/d.txt": "5",
            "outer/e.txt": "7",
            "outer/inner/c.txt": "6",
        })

    def assert_unchanged_head(self, repo):
        assert repo.refs.read_head() == self.head_oid

    def test_restores_removed_file_in_index(self, legit_cmd, repo, repo_path):
        legit_cmd("reset", "a.txt")
        self.assert_index(repo, {
            "a.txt": "1",
            "outer/b.txt": "4",
            "outer/d.txt": "5",
            "outer/inner/c.txt": "6",
        })
        self.assert_unchanged_head(repo)
        self.assert_unchanged_workspace(repo_path)

    def test_resets_modified_file_in_index(self, legit_cmd, repo, repo_path):
        legit_cmd("reset", "outer/inner")
        self.assert_index(repo, {
            "outer/b.txt": "4",
            "outer/d.txt": "5",
            "outer/inner/c.txt": "3",
        })
        self.assert_unchanged_head(repo)
        self.assert_unchanged_workspace(repo_path)

    def test_removes_added_file_from_index(self, legit_cmd, repo, repo_path):
        legit_cmd("reset", "outer/d.txt")
        self.assert_index(repo, {
            "outer/b.txt": "4",
            "outer/inner/c.txt": "6",
        })
        self.assert_unchanged_head(repo)
        self.assert_unchanged_workspace(repo_path)

    def test_resets_file_to_specific_commit(self, legit_cmd, repo, repo_path):
        legit_cmd("reset", "@^", "outer/b.txt")
        self.assert_index(repo, {
            "outer/b.txt": "2",
            "outer/d.txt": "5",
            "outer/inner/c.txt": "6",
        })
        self.assert_unchanged_head(repo)
        self.assert_unchanged_workspace(repo_path)

    def test_resets_whole_index(self, legit_cmd, repo, repo_path):
        legit_cmd("reset")
        self.assert_index(repo, {
            "a.txt": "1",
            "outer/b.txt": "4",
            "outer/inner/c.txt": "3",
        })
        self.assert_unchanged_head(repo)
        self.assert_unchanged_workspace(repo_path)

    def test_resets_index_and_moves_head(self, legit_cmd, repo, repo_path):
        legit_cmd("reset", "@^")
        self.assert_index(repo, {
            "a.txt": "1",
            "outer/b.txt": "2",
            "outer/inner/c.txt": "3",
        })
        # HEAD advanced one commit back
        assert repo.refs.read_head() == repo.database.load(self.head_oid).parent
        self.assert_unchanged_workspace(repo_path)

    def test_soft_reset_moves_head_only(self, legit_cmd, repo, repo_path):
        legit_cmd("reset", "--soft", "@^")
        # Index unchanged
        self.assert_index(repo, {
            "outer/b.txt": "4",
            "outer/d.txt": "5",
            "outer/inner/c.txt": "6",
        })
        assert repo.refs.read_head() == repo.database.load(self.head_oid).parent
        self.assert_unchanged_workspace(repo_path)

    def test_hard_reset_index_and_workspace(self, write_file, delete, legit_cmd, repo, repo_path):
        # Make extra changes in working tree
        write_file("a.txt/nested", "remove me")
        write_file("outer/b.txt", "10")
        delete("outer/inner")
        legit_cmd("reset", "--hard")
        self.assert_unchanged_head(repo)
        self.assert_index(repo, {
            "a.txt": "1",
            "outer/b.txt": "4",
            "outer/inner/c.txt": "3",
        })
        cmd, _, stdout, _ = legit_cmd("status", "--porcelain")
        assert_stdout(stdout, "?? outer/e.txt\n")

    def test_return_to_orig_head(self, legit_cmd, repo):
        legit_cmd("reset", "--hard", "@^")
        self.assert_index(repo, {
            "a.txt": "1",
            "outer/b.txt": "2",
            "outer/inner/c.txt": "3",
        })
        legit_cmd("reset", "--hard", "ORIG_HEAD")
        self.assert_index(repo, {
            "a.txt": "1",
            "outer/b.txt": "4",
            "outer/inner/c.txt": "3",
        })

