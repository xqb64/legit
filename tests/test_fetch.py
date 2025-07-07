import os
import shutil
import tempfile
import subprocess
from io import StringIO
from pathlib import Path
from typing import List, Tuple, Optional

import pytest

from legit.command import Command
from legit.repository import Repository
from legit.rev_list import RevList
from tests.cmd_helpers import (
    assert_status,
    assert_stderr,
    assert_workspace,
)

# Match the Ruby test‑suite behaviour: always disable progress output.
os.environ["NO_PROGRESS"] = "1"


# ---------------------------------------------------------------------------
# Helper utilities (mirrors helpers used by the Ruby suite)
# ---------------------------------------------------------------------------

def assert_object_count(repo_path: Path, expected: int) -> None:
    """Assert that exactly *expected* loose/packed objects live under .git/objects."""
    count = 0
    for obj_path in (repo_path / ".git" / "objects").rglob("*"):
        if obj_path.is_file():
            count += 1
    assert count == expected, (
        f"Expected {expected} loose/packed objects, found {count}"
    )


class ProcResult:
    """Duck‑type Ruby's `Process::Status` that CommandHelper expects."""

    def __init__(self, returncode: int):
        self.status = returncode  # Ruby's `$?.exitstatus` analogue


class RemoteRepo:
    """A disposable remote repository used by the tests (parity with Ruby RemoteRepo)."""

    def __init__(self, repo_path: Path, legit_cmd):
        self.repo_path: Path = repo_path
        self._legit_cmd = legit_cmd
        self._legit_cmd("init", str(self.repo_path))
        self.repo: Repository = Repository(self.repo_path / ".git")

    # ---------------------------------------------------------------------
    # Convenience helpers (keep names identical to Ruby helpers)
    # ---------------------------------------------------------------------
    def write_file(self, name: str, contents: str) -> None:
        dest = self.repo_path / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(contents)

    def write_commit(self, message: str) -> None:
        """Create a commit whose message *and* blob‑content equal *message*."""
        self.write_file(f"{message}.txt", message)
        self._legit_cmd("add", ".")
        self._legit_cmd("commit", "-m", message)

    # Helpers that the main test‑class uses to mutate remote history
    def advance_one_commit(self) -> None:
        """Fast‑forward the remote by appending a commit."""
        self.write_file("one.txt", "changed")
        self._legit_cmd("add", ".")
        self._legit_cmd("commit", "-m", "changed")

    def diverge_one_commit(self) -> None:
        """Force‑update remote/master by *amending* its tip (non‑fast‑forward)."""
        self.write_file("one.txt", "changed")
        self._legit_cmd("add", ".")
        self._legit_cmd("commit", "--amend")


# ---------------------------------------------------------------------------
# Fixtures shared by every test
# ---------------------------------------------------------------------------

def _legit_binary() -> str:
    path = shutil.which("legit")
    assert path, "`legit` executable not found in PATH!"
    return path


@pytest.fixture
def legit_cmd():
    """Spawn the legit CLI just like Ruby's `jit_cmd` helper does."""

    def _call_legit(*argv: str,
                    env: Optional[dict] = None,
                    cwd: Optional[Path] = None,
                    stdin_data: str = "") -> Tuple[ProcResult, StringIO, StringIO, StringIO]:
        child_env = os.environ.copy()
        if env:
            child_env.update(env)

        proc = subprocess.Popen(
            [_legit_binary(), *argv],
            env=child_env,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=-1,
        )
        stdout_val, stderr_val = proc.communicate(input=stdin_data)
        return (
            ProcResult(proc.returncode),
            StringIO(stdin_data),
            StringIO(stdout_val),
            StringIO(stderr_val),
        )

    return _call_legit


@pytest.fixture
def remote_repo(tmp_path: Path, legit_cmd):
    """Yield a RemoteRepo whose lifetime is bound to the test function."""
    repo = RemoteRepo(tmp_path / "remote", legit_cmd)
    yield repo
    # Explicit cleanup for readability (tmp_path is removed by pytest anyway)
    shutil.rmtree(repo.repo_path, ignore_errors=True)


@pytest.fixture
def repo_path(tmp_path: Path) -> Path:
    """Provide an *empty* working directory initialised as a legit repo."""
    path = tmp_path / "local"
    subprocess.run([_legit_binary(), "init", str(path)]) 
    return path


@pytest.fixture
def repo(repo_path: Path) -> Repository:
    return Repository(repo_path / ".git")


# ---------------------------------------------------------------------------
# Thin wrapper around RevList to replicate Ruby's helper exactly
# ---------------------------------------------------------------------------

def commits(repo: Repository, revs: List[str], options: Optional[dict] = None) -> List[str]:
    if options is None:
        options = {}
    out: List[str] = []
    for commit, _ in RevList(repo, revs, options).each():
        out.append(repo.database.short_oid(commit.oid))
    return out


# ---------------------------------------------------------------------------
# Test‑suite – mirrors Ruby's structure as closely as pytest allows
# ---------------------------------------------------------------------------

class TestFetchSingleBranch:
    """Behaviour when the *remote* only has its default `master` branch."""

    # ---------------------------------------------------------------------
    # Primary setup: create remote with 3 commits and add it as `origin`.
    # ---------------------------------------------------------------------
    @pytest.fixture(autouse=True)
    def _setup(self, remote_repo: RemoteRepo, repo_path: Path, legit_cmd):
        self.remote: RemoteRepo = remote_repo
        for msg in ["one", "dir/two", "three"]:
            self.remote.write_commit(msg)

        # Wire‑up remote → local
        legit_cmd("remote", "add", "origin", f"file://{self.remote.repo_path}")
        legit_cmd(
            "config",
            "remote.origin.uploadpack",
            f"{_legit_binary()} upload-pack",
        )

        self.repo_path: Path = repo_path
        self.repo: Repository = Repository(repo_path / ".git")
        self.legit_cmd = legit_cmd

    # ------------------------------------------------------------------
    # Straightforward happy‑path tests
    # ------------------------------------------------------------------
    def test_displays_new_branch_being_fetched(self):
        cmd, _, _, stderr = self.legit_cmd("fetch")
        assert_status(cmd, 0)
        assert_stderr(
            stderr,
            (
                f"From file://{self.remote.repo_path}\n"
                " * [new branch] master -> origin/master\n"
            ),
        )

    def test_maps_remote_heads_to_local_origin(self):
        self.legit_cmd("fetch")
        assert (
            self.remote.repo.refs.read_ref("refs/heads/master")
            == self.repo.refs.read_ref("refs/remotes/origin/master")
        )

    def test_maps_remote_heads_to_different_local_ref(self):
        self.legit_cmd(
            "fetch",
            "origin",
            "refs/heads/*:refs/remotes/other/prefix-*",
        )
        assert (
            self.remote.repo.refs.read_ref("refs/heads/master")
            == self.repo.refs.read_ref("refs/remotes/other/prefix-master")
        )

    def test_accepts_short_hand_refs_in_refspec(self):
        self.legit_cmd("fetch", "origin", "master:topic")
        assert (
            self.remote.repo.refs.read_ref("refs/heads/master")
            == self.repo.refs.read_ref("refs/heads/topic")
        )

    def test_accepts_short_hand_head_refs_in_refspec(self):
        self.legit_cmd("fetch", "origin", "master:heads/topic")
        assert (
            self.remote.repo.refs.read_ref("refs/heads/master")
            == self.repo.refs.read_ref("refs/heads/topic")
        )

    def test_accepts_short_hand_remote_refs_in_refspec(self):
        self.legit_cmd("fetch", "origin", "master:remotes/topic")
        assert (
            self.remote.repo.refs.read_ref("refs/heads/master")
            == self.repo.refs.read_ref("refs/remotes/topic")
        )

    def test_does_not_create_other_local_refs(self):
        self.legit_cmd("fetch")
        expected = ["HEAD", "refs/remotes/origin/master"]
        assert sorted(r.path for r in self.repo.refs.list_all_refs()) == expected

    def test_retrieves_all_commits_from_remote_history(self):
        self.legit_cmd("fetch")
        assert commits(self.remote.repo, ["master"]) == commits(
            self.repo, ["origin/master"]
        )

    def test_retrieves_enough_information_to_checkout_remote_commits(self):
        self.legit_cmd("fetch")

        self.legit_cmd("checkout", "origin/master^")
        assert_workspace(
            self.repo_path,
            {"one.txt": "one", "dir/two.txt": "dir/two"},
        )

        self.legit_cmd("checkout", "origin/master")
        assert_workspace(
            self.repo_path,
            {
                "one.txt": "one",
                "dir/two.txt": "dir/two",
                "three.txt": "three",
            },
        )

        self.legit_cmd("checkout", "origin/master^^")
        assert_workspace(self.repo_path, {"one.txt": "one"})

    # ------------------------------------------------------------------
    # Tests that depend on fetch.unpackLimit
    # ------------------------------------------------------------------
    class TestWithUnpackLimit:
        @pytest.fixture(autouse=True)
        def _config_unpack_limit(self, request):
            outer = request.cls  # ancestor TestFetchSingleBranch instance
            outer.legit_cmd("config", "fetch.unpackLimit", "5")

        def test_keeps_pack_on_disk_with_index(self, request):
            outer = request.cls
            outer.legit_cmd("fetch")
            assert_object_count(outer.repo_path, 2)

        def test_can_load_commits_from_stored_pack(self, request):
            outer = request.cls
            outer.legit_cmd("fetch")
            assert commits(outer.remote.repo, ["master"]) == commits(
                outer.repo, ["origin/master"]
            )

    # ------------------------------------------------------------------
    # Helper methods to mutate the remote's history (shared by scenarios)
    # ------------------------------------------------------------------
    def _advance_remote(self):
        self.remote.advance_one_commit()

    def _diverge_remote(self):
        self.remote.diverge_one_commit()

    # ------------------------------------------------------------------
    # Scenario: remote ref is *ahead* of its local counterpart (fast‑forward)
    # ------------------------------------------------------------------
    def test_displays_fast_forward_when_remote_is_ahead(self):
        self.legit_cmd("fetch")  # bring local in‑sync first
        local_head = commits(self.repo, ["origin/master"])[0]

        self._advance_remote()
        remote_head = commits(self.remote.repo, ["master"])[0]

        cmd, _, _, stderr = self.legit_cmd("fetch")
        assert_status(cmd, 0)
        assert_stderr(
            stderr,
            (
                f"From file://{self.remote.repo_path}\n"
                f"   {local_head}..{remote_head} master -> origin/master\n"
            ),
        )

    # ------------------------------------------------------------------
    # Scenario: remote ref has *diverged* (non‑fast‑forward)
    # ------------------------------------------------------------------
    def test_displays_forced_update_when_remote_has_diverged(self):
        self.legit_cmd("fetch")
        local_head = commits(self.repo, ["origin/master"])[0]

        self._diverge_remote()
        remote_head = commits(self.remote.repo, ["master"])[0]

        cmd, _, _, stderr = self.legit_cmd("fetch")
        assert_status(cmd, 0)
        assert_stderr(
            stderr,
            (
                f"From file://{self.remote.repo_path}\n"
                f" + {local_head}...{remote_head} master -> origin/master (forced update)\n"
            ),
        )

    def test_displays_forced_update_if_requested(self):
        self.legit_cmd("fetch")
        local_head = commits(self.repo, ["origin/master"])[0]
        self._diverge_remote()
        remote_head = commits(self.remote.repo, ["master"])[0]

        cmd, _, _, stderr = self.legit_cmd(
            "fetch",
            "-f",
            "origin",
            "refs/heads/*:refs/remotes/origin/*",
        )
        assert_status(cmd, 0)
        assert_stderr(
            stderr,
            (
                f"From file://{self.remote.repo_path}\n"
                f" + {local_head}...{remote_head} master -> origin/master (forced update)\n"
            ),
        )

    def test_updates_local_remote_ref_after_divergence(self):
        """After a diverged fetch, the remote tracking branch should move."""
        self.legit_cmd("fetch")
        self._diverge_remote()
        remote_head = commits(self.remote.repo, ["master"])[0]

        # A *regular* fetch should force‑update the tracking ref.
        self.legit_cmd("fetch")
        assert commits(self.repo, ["origin/master"])[0] == remote_head

    # --------------------------------------------------------------
    # Nested scenario: explicit refspec *without* force flag
    # --------------------------------------------------------------
    def _non_forced_fetch(self):
        """Helper that performs the non‑forced fetch and returns artefacts."""
        self.legit_cmd("fetch")  # sync once
        self._diverge_remote()
        local_head = commits(self.repo, ["origin/master"])[0]
        remote_head = commits(self.remote.repo, ["master"])[0]
        cmd, _, _, stderr = self.legit_cmd(
            "fetch",
            "origin",
            "refs/heads/*:refs/remotes/origin/*",
        )
        return cmd, stderr, local_head, remote_head

    def test_non_forced_fetch_exits_with_error(self):
        cmd, _, _, _ = self._non_forced_fetch()
        assert_status(cmd, 1)

    def test_non_forced_fetch_displays_rejection(self):
        cmd, stderr, local_head, _ = self._non_forced_fetch()
        assert_status(cmd, 1)
        assert_stderr(
            stderr,
            (
                f"From file://{self.remote.repo_path}\n"
                " ! [rejected] master -> origin/master (non-fast-forward)\n"
            ),
        )

    def test_non_forced_fetch_does_not_update_local_ref(self):
        _, _, local_head, _ = self._non_forced_fetch()
        assert commits(self.repo, ["origin/master"])[0] == local_head


# =============================================================================
# Multiple‑branch scenario – mirrors Ruby counterpart exactly
# =============================================================================

class TestFetchMultipleBranches:
    """Behaviour when the *remote* has both `master` and `topic` branches."""

    @pytest.fixture(autouse=True)
    def _setup(self, remote_repo: RemoteRepo, repo_path: Path, legit_cmd):
        self.remote: RemoteRepo = remote_repo
        for msg in ["one", "dir/two", "three"]:
            self.remote.write_commit(msg)

        # Create and populate "topic" branch
        self.remote._legit_cmd("branch", "topic", "@^")
        self.remote._legit_cmd("checkout", "topic")
        self.remote.write_commit("four")

        # Add as origin
        legit_cmd("remote", "add", "origin", f"file://{self.remote.repo_path}")
        legit_cmd(
            "config",
            "remote.origin.uploadpack",
            f"{_legit_binary()} upload-pack",
        )

        self.repo_path: Path = repo_path
        self.repo: Repository = Repository(repo_path / ".git")
        self.legit_cmd = legit_cmd

    # ------------------------------------------------------------------
    # Happy‑path tests
    # ------------------------------------------------------------------
    def test_displays_new_branches_being_fetched(self):
        cmd, _, _, stderr = self.legit_cmd("fetch")
        assert_status(cmd, 0)
        assert_stderr(
            stderr,
            (
                f"From file://{self.remote.repo_path}\n"
                " * [new branch] master -> origin/master\n"
                " * [new branch] topic -> origin/topic\n"
            ),
        )

    def test_maps_remote_heads_to_local_origin(self):
        self.legit_cmd("fetch")
        remote_master = self.remote.repo.refs.read_ref("refs/heads/master")
        remote_topic = self.remote.repo.refs.read_ref("refs/heads/topic")
        assert remote_master != remote_topic  # sanity check
        assert remote_master == self.repo.refs.read_ref("refs/remotes/origin/master")
        assert remote_topic == self.repo.refs.read_ref("refs/remotes/origin/topic")

    def test_maps_remote_heads_to_different_local_ref(self):
        self.legit_cmd(
            "fetch",
            "origin",
            "refs/heads/*:refs/remotes/other/prefix-*",
        )
        assert (
            self.remote.repo.refs.read_ref("refs/heads/master")
            == self.repo.refs.read_ref("refs/remotes/other/prefix-master")
        )
        assert (
            self.remote.repo.refs.read_ref("refs/heads/topic")
            == self.repo.refs.read_ref("refs/remotes/other/prefix-topic")
        )

    def test_does_not_create_other_local_refs(self):
        self.legit_cmd("fetch")
        assert sorted(r.path for r in self.repo.refs.list_all_refs()) == [
            "HEAD",
            "refs/remotes/origin/master",
            "refs/remotes/origin/topic",
        ]

    def test_retrieves_all_commits_from_remote_history(self):
        self.legit_cmd("fetch")
        assert_object_count(self.repo_path, 13)
        remote_commits = commits(self.remote.repo, [], {"all": True})
        assert len(remote_commits) == 4
        assert remote_commits == commits(self.repo, [], {"all": True})

    def test_retrieves_enough_information_to_checkout_remote_commits(self):
        self.legit_cmd("fetch")

        self.legit_cmd("checkout", "origin/master")
        assert_workspace(
            self.repo_path,
            {
                "one.txt": "one",
                "dir/two.txt": "dir/two",
                "three.txt": "three",
            },
        )

        self.legit_cmd("checkout", "origin/topic")
        assert_workspace(
            self.repo_path,
            {
                "one.txt": "one",
                "dir/two.txt": "dir/two",
                "four.txt": "four",
            },
        )

    # --------------------------------------------------------------
    # Scenario: requesting a specific branch via globbed refspec
    # --------------------------------------------------------------
    class TestFetchSpecificBranch:
        @pytest.fixture(autouse=True)
        def _fetch_topic(self, request):
            outer = request.cls  # TestFetchMultipleBranches instance
            outer.legit_cmd(
                "fetch",
                "origin",
                "+refs/heads/*ic:refs/remotes/origin/*",
            )

        def test_displays_branch_being_fetched(self, request):
            outer = request.cls
            stderr = outer.legit_cmd(
                "fetch",
                "origin",
                "+refs/heads/*ic:refs/remotes/origin/*",
            )[3]
            assert_stderr(
                stderr,
                (
                    f"From file://{outer.remote.repo_path}\n"
                    " * [new branch] topic -> origin/top\n"
                ),
            )

        def test_does_not_create_other_local_refs(self, request):
            outer = request.cls
            assert sorted(r.path for r in outer.repo.refs.list_all_refs()) == [
                "HEAD",
                "refs/remotes/origin/top",
            ]

        def test_retrieves_only_commits_from_fetched_branch(self, request):
            outer = request.cls
            assert_object_count(outer.repo_path, 10)
            remote_commits = commits(outer.remote.repo, ["topic"])
            assert len(remote_commits) == 3
            assert remote_commits == commits(outer.repo, [], {"all": True})


