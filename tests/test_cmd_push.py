import shutil
from pathlib import Path
from typing import Any, Callable, Generator, TypeAlias, cast

import pytest

from legit.repository import Repository
from legit.rev_list import RevList
from tests.cmd_helpers import (
    assert_status,
    assert_stderr,
)
from tests.cmd_helpers import (
    assert_workspace as _assert_workspace,
)
from tests.conftest import (
    LegitCmd,
    WriteFile,
)
from tests.remote_repo import RemoteRepo

CreateRemoteRepo: TypeAlias = Callable[[str], RemoteRepo]
WriteCommit: TypeAlias = Callable[[str], None]


@pytest.fixture
def create_remote_repo(repo_path: Path) -> Generator[CreateRemoteRepo]:
    created_remote_paths = []

    def _create_remote_repo(name: str) -> RemoteRepo:
        remote_repo = RemoteRepo(name)
        remote_repo_path = remote_repo.path(repo_path)

        created_remote_paths.append(remote_repo_path)

        remote_repo.legit_cmd(repo_path, "init", str(remote_repo_path))

        remote_repo.legit_cmd(repo_path, "config", "receive.denyCurrentBranch", "false")
        remote_repo.legit_cmd(repo_path, "config", "receive.denyDeleteCurrent", "false")

        return remote_repo

    yield _create_remote_repo

    for path in created_remote_paths:
        if path.exists() and path.is_dir():
            shutil.rmtree(path)


@pytest.fixture
def write_commit(write_file: WriteFile, legit_cmd: LegitCmd) -> WriteCommit:
    def _write_commit(msg: str) -> None:
        write_file(f"{msg}.txt", msg)
        legit_cmd("add", ".")
        legit_cmd("commit", "-m", msg)

    return _write_commit


def commits(
    repo: Repository, revs: list[str], options: dict[str, Any] | None = None
) -> list[str]:
    if options is None:
        options = {}
    return [
        repo.database.short_oid(commit.oid)
        for commit, _ in RevList(repo, revs, options).each()
    ]


def assert_object_count(repo_root: Path, expected: int) -> None:
    count = sum(1 for p in (repo_root / ".git" / "objects").rglob("*") if p.is_file())
    assert count == expected, (
        f"object-count mismatch – expected {expected}, found {count}"
    )


def assert_refs(repo: Repository, refs: list[str]) -> None:
    assert refs == sorted([ref.path for ref in repo.refs.list_all_refs()])


@pytest.fixture
def legit_path() -> Path:
    return Path(shutil.which("legit") or "legit")


def assert_workspace(repo_root: Path, contents: dict[str, str]) -> None:
    _assert_workspace(repo_root, contents)


class TestSingleBranchInitialPush:
    @pytest.fixture(autouse=True)
    def _setup(
        self,
        create_remote_repo: CreateRemoteRepo,
        write_commit: WriteCommit,
        legit_cmd: LegitCmd,
        legit_path: Path,
    ) -> None:
        self.remote = create_remote_repo("push-remote")

        for msg in ("one", "dir/two", "three"):
            write_commit(msg)

        legit_cmd(
            "remote", "add", "origin", f"file://{cast(Path, self.remote.repo_path)}"
        )
        legit_cmd(
            "config",
            "remote.origin.receivepack",
            f"{legit_path} receive-pack",
        )
        legit_cmd(
            "config",
            "remote.origin.uploadpack",
            f"{legit_path} upload-pack",
        )

    def test_displays_new_branch_being_pushed(self, legit_cmd: LegitCmd) -> None:
        cmd, *_, stderr = legit_cmd("push", "origin", "master")
        assert_status(cmd, 0)
        expected = f"To file://{cast(Path, self.remote.repo_path)}\n * [new branch] master -> master\n"
        assert_stderr(stderr, expected)

    def test_maps_local_head_to_remote(
        self, legit_cmd: LegitCmd, repo: Repository
    ) -> None:
        legit_cmd("push", "origin", "master")
        assert repo.refs.read_ref(
            "refs/heads/master"
        ) == self.remote.repo.refs.read_ref("refs/heads/master")

    def test_maps_local_head_to_different_remote_ref(
        self, legit_cmd: LegitCmd, repo: Repository
    ) -> None:
        legit_cmd("push", "origin", "master:refs/heads/other")
        assert repo.refs.read_ref(
            "refs/heads/master"
        ) == self.remote.repo.refs.read_ref("refs/heads/other")

    def test_does_not_create_any_other_remote_refs(self, legit_cmd: LegitCmd) -> None:
        legit_cmd("push", "origin", "master")
        assert_refs(self.remote.repo, ["HEAD", "refs/heads/master"])

    def test_sends_all_commits_from_local_history(
        self, legit_cmd: LegitCmd, repo: Repository
    ) -> None:
        legit_cmd("push", "origin", "master")
        assert_commits = repo, self.remote.repo
        assert commits(assert_commits[0], ["master"]) == commits(
            assert_commits[1], ["master"]
        )

    def test_sends_enough_information_to_checkout_commits(
        self, legit_cmd: LegitCmd, repo_path: Path
    ) -> None:
        legit_cmd("push", "origin", "master")

        self.remote.legit_cmd(repo_path, "reset", "--hard")

        self.remote.legit_cmd(repo_path, "checkout", "master^")
        assert_workspace(
            cast(Path, self.remote.repo_path),
            {"one.txt": "one", "dir/two.txt": "dir/two"},
        )

        self.remote.legit_cmd(repo_path, "checkout", "master")
        assert_workspace(
            cast(Path, self.remote.repo_path),
            {
                "one.txt": "one",
                "dir/two.txt": "dir/two",
                "three.txt": "three",
            },
        )

        self.remote.legit_cmd(repo_path, "checkout", "master^^")
        assert_workspace(cast(Path, self.remote.repo_path), {"one.txt": "one"})

    def test_pushes_ancestor_of_current_head(
        self, legit_cmd: LegitCmd, repo: Repository
    ) -> None:
        cmd, *_, stderr = legit_cmd("push", "origin", "@~1:master")
        assert_status(cmd, 0)
        local_head = commits(repo, ["master^"])[0]
        expected = f"To file://{cast(Path, self.remote.repo_path)}\n * [new branch] @~1 -> master\n"
        assert_stderr(stderr, expected)
        assert commits(repo, ["master^"])[0] == commits(self.remote.repo, ["master"])[0]


class TestSingleBranchAfterSuccessfulPush:
    @pytest.fixture(autouse=True)
    def _setup(
        self,
        create_remote_repo: CreateRemoteRepo,
        write_commit: WriteCommit,
        legit_cmd: LegitCmd,
        legit_path: Path,
    ) -> None:
        self.remote = create_remote_repo("push-remote")
        for msg in ("one", "dir/two", "three"):
            write_commit(msg)
        legit_cmd(
            "remote", "add", "origin", f"file://{cast(Path, self.remote.repo_path)}"
        )
        legit_cmd("config", "remote.origin.receivepack", f"{legit_path} receive-pack")
        legit_cmd("push", "origin", "master")

    def test_everything_up_to_date_on_second_push(self, legit_cmd: LegitCmd) -> None:
        cmd, *_, stderr = legit_cmd("push", "origin", "master")
        assert_status(cmd, 0)
        assert_stderr(stderr, "Everything up-to-date\n")
        assert_refs(self.remote.repo, ["HEAD", "refs/heads/master"])

    def test_deletes_remote_branch_by_refspec(
        self, legit_cmd: LegitCmd, repo: Repository
    ) -> None:
        cmd, *_, stderr = legit_cmd("push", "origin", ":master")
        assert_status(cmd, 0)
        expected = (
            f"To file://{cast(Path, self.remote.repo_path)}\n - [deleted] master\n"
        )
        assert_stderr(stderr, expected)
        assert_refs(repo, ["HEAD", "refs/heads/master"])
        assert_refs(self.remote.repo, ["HEAD"])


class TestSingleBranchLocalAhead:
    @pytest.fixture(autouse=True)
    def _setup(
        self,
        repo: Repository,
        create_remote_repo: CreateRemoteRepo,
        write_commit: WriteCommit,
        legit_cmd: LegitCmd,
        legit_path: Path,
    ) -> None:
        self.remote = create_remote_repo("push-remote")
        for msg in ("one", "dir/two", "three"):
            write_commit(msg)
        legit_cmd(
            "remote", "add", "origin", f"file://{cast(Path, self.remote.repo_path)}"
        )
        legit_cmd("config", "remote.origin.receivepack", f"{legit_path} receive-pack")
        legit_cmd("push", "origin", "master")
        write_commit("changed")
        self.local_head = commits(repo, ["master"])[0]
        self.remote_head = commits(self.remote.repo, ["master"])[0]

    def test_displays_fast_forward_on_changed_branch(self, legit_cmd: LegitCmd) -> None:
        cmd, *_, stderr = legit_cmd("push", "origin", "master")
        assert_status(cmd, 0)
        expected = (
            f"To file://{cast(Path, self.remote.repo_path)}\n"
            f"   {self.remote_head}..{self.local_head} master -> master\n"
        )
        assert_stderr(stderr, expected)

    def test_succeeds_when_remote_denies_non_fast_forward(
        self, legit_cmd: LegitCmd, repo_path: Path
    ) -> None:
        self.remote.legit_cmd(
            repo_path, "config", "receive.denyNonFastForwards", "true"
        )
        cmd, *_, stderr = legit_cmd("push", "origin", "master")
        assert_status(cmd, 0)
        expected = (
            f"To file://{cast(Path, self.remote.repo_path)}\n"
            f"   {self.remote_head}..{self.local_head} master -> master\n"
        )
        assert_stderr(stderr, expected)


class TestSingleBranchRemoteDiverged:
    @pytest.fixture(autouse=True)
    def _setup(
        self,
        repo: Repository,
        create_remote_repo: CreateRemoteRepo,
        write_commit: WriteCommit,
        legit_cmd: LegitCmd,
        legit_path: Path,
        repo_path: Path,
    ) -> None:
        self.remote = create_remote_repo("push-remote")
        for msg in ("one", "dir/two", "three"):
            write_commit(msg)
        legit_cmd(
            "remote", "add", "origin", f"file://{cast(Path, self.remote.repo_path)}"
        )
        legit_cmd("config", "remote.origin.receivepack", f"{legit_path} receive-pack")
        legit_cmd("push", "origin", "master")

        self.remote.write_file("one.txt", "changed")
        self.remote.legit_cmd(repo_path, "add", ".")
        self.remote.legit_cmd(repo_path, "commit", "--amend")

        self.local_head = commits(repo, ["master"])[0]
        self.remote_head = commits(self.remote.repo, ["master"])[0]

    def test_forced_update_if_requested(self, legit_cmd: LegitCmd) -> None:
        cmd, *_, stderr = legit_cmd("push", "origin", "master", "-f")
        assert_status(cmd, 0)
        expected = (
            f"To file://{cast(Path, self.remote.repo_path)}\n"
            f" + {self.remote_head}...{self.local_head} master -> master (forced update)\n"
        )
        assert_stderr(stderr, expected)

    def test_updates_local_origin_ref(
        self, legit_cmd: LegitCmd, repo: Repository
    ) -> None:
        legit_cmd("push", "origin", "master", "-f")
        assert self.local_head == commits(repo, ["origin/master"])[0]

    def test_deletes_remote_branch_by_refspec(self, legit_cmd: LegitCmd) -> None:
        cmd, *_, stderr = legit_cmd("push", "origin", ":master")
        assert_status(cmd, 0)
        expected = (
            f"To file://{cast(Path, self.remote.repo_path)}\n - [deleted] master\n"
        )
        assert_stderr(stderr, expected)
        assert_refs(self.remote.repo, ["HEAD"])

    def test_rejected_without_force(self, legit_cmd: LegitCmd) -> None:
        cmd, *_, stderr = legit_cmd("push", "origin", "master")
        assert_status(cmd, 1)
        expected = (
            f"To file://{cast(Path, self.remote.repo_path)}\n"
            " ! [rejected] master -> master (fetch first)\n"
        )
        assert_stderr(stderr, expected)

    def test_rejection_message_after_fetch(self, legit_cmd: LegitCmd) -> None:
        legit_cmd("fetch")
        cmd, *_, stderr = legit_cmd("push", "origin", "master")
        expected = (
            f"To file://{cast(Path, self.remote.repo_path)}\n"
            " ! [rejected] master -> master (non-fast-forward)\n"
        )
        assert_stderr(stderr, expected)

    def test_does_not_update_local_origin_ref_on_reject(self, repo: Repository) -> None:
        assert self.local_head == commits(repo, ["origin/master"])[0]

    def test_remote_denies_non_fast_forward(
        self, legit_cmd: LegitCmd, repo_path: Path
    ) -> None:
        self.remote.legit_cmd(
            repo_path, "config", "receive.denyNonFastForwards", "true"
        )
        legit_cmd("fetch")
        cmd, *_, stderr = legit_cmd("push", "origin", "master", "-f")
        assert_status(cmd, 1)
        expected = (
            f"To file://{cast(Path, self.remote.repo_path)}\n"
            " ! [rejected] master -> master (non-fast-forward)\n"
        )
        assert_stderr(stderr, expected)


class TestRemoteDeniesUpdatingCurrentBranch:
    @pytest.fixture(autouse=True)
    def _setup(
        self,
        create_remote_repo: CreateRemoteRepo,
        write_commit: WriteCommit,
        legit_cmd: LegitCmd,
        legit_path: Path,
        repo_path: Path,
    ) -> None:
        self.remote = create_remote_repo("push-remote")

        for msg in ("one", "dir/two", "three"):
            write_commit(msg)

        legit_cmd(
            "remote", "add", "origin", f"file://{cast(Path, self.remote.repo_path)}"
        )
        legit_cmd("config", "remote.origin.receivepack", f"{legit_path} receive-pack")

        self.remote.legit_cmd(
            repo_path, "config", "--unset", "receive.denyCurrentBranch"
        )

    def test_rejects_push(self, legit_cmd: LegitCmd) -> None:
        cmd, *_, stderr = legit_cmd("push", "origin", "master")
        assert_status(cmd, 1)
        expected = (
            f"To file://{cast(Path, self.remote.repo_path)}\n"
            " ! [rejected] master -> master (branch is currently checked out)\n"
        )
        assert_stderr(stderr, expected)

    def test_does_not_update_remote_ref(
        self, legit_cmd: LegitCmd, repo: Repository
    ) -> None:
        legit_cmd("push", "origin", "master")
        assert repo.refs.read_ref("refs/heads/master") is not None
        assert self.remote.repo.refs.read_ref("refs/heads/master") is None

    def test_does_not_update_local_origin_ref(
        self, legit_cmd: LegitCmd, repo: Repository
    ) -> None:
        legit_cmd("push", "origin", "master")
        assert repo.refs.read_ref("refs/remotes/origin/master") is None


class TestRemoteDeniesDeletingCurrentBranch:
    @pytest.fixture(autouse=True)
    def _setup(
        self,
        create_remote_repo: CreateRemoteRepo,
        write_commit: WriteCommit,
        legit_cmd: LegitCmd,
        legit_path: Path,
        repo_path: Path,
    ) -> None:
        self.remote = create_remote_repo("push-remote")
        for msg in ("one", "dir/two", "three"):
            write_commit(msg)
        legit_cmd(
            "remote", "add", "origin", f"file://{cast(Path, self.remote.repo_path)}"
        )
        legit_cmd("config", "remote.origin.receivepack", f"{legit_path} receive-pack")
        legit_cmd("push", "origin", "master")
        self.remote.legit_cmd(
            repo_path, "config", "--unset", "receive.denyDeleteCurrent"
        )

    def test_rejects_deletion(self, legit_cmd: LegitCmd) -> None:
        cmd, *_, stderr = legit_cmd("push", "origin", ":master")
        assert_status(cmd, 1)
        expected = (
            f"To file://{cast(Path, self.remote.repo_path)}\n"
            " ! [rejected] master (deletion of the current branch prohibited)\n"
        )
        assert_stderr(stderr, expected)

    def test_does_not_delete_remote_ref(self, legit_cmd: LegitCmd) -> None:
        legit_cmd("push", "origin", ":master")
        assert self.remote.repo.refs.read_ref("refs/heads/master") is not None

    def test_does_not_delete_local_origin_ref(self, repo: Repository) -> None:
        assert repo.refs.read_ref("refs/remotes/origin/master") is not None


class TestRemoteDeniesDeletingAnyBranch:
    @pytest.fixture(autouse=True)
    def _setup(
        self,
        create_remote_repo: CreateRemoteRepo,
        write_commit: WriteCommit,
        legit_cmd: LegitCmd,
        legit_path: Path,
        repo_path: Path,
    ) -> None:
        self.remote = create_remote_repo("push-remote")
        for msg in ("one", "dir/two", "three"):
            write_commit(msg)
        legit_cmd(
            "remote", "add", "origin", f"file://{cast(Path, self.remote.repo_path)}"
        )
        legit_cmd("config", "remote.origin.receivepack", f"{legit_path} receive-pack")
        legit_cmd("push", "origin", "master")
        self.remote.legit_cmd(repo_path, "config", "receive.denyDeletes", "true")

    def test_rejects_deletion(self, legit_cmd: LegitCmd) -> None:
        cmd, *_, stderr = legit_cmd("push", "origin", ":master")
        assert_status(cmd, 1)
        expected = (
            f"To file://{cast(Path, self.remote.repo_path)}\n"
            " ! [rejected] master (deletion prohibited)\n"
        )
        assert_stderr(stderr, expected)

    def test_does_not_delete_remote_ref(self, legit_cmd: LegitCmd) -> None:
        legit_cmd("push", "origin", ":master")
        assert self.remote.repo.refs.read_ref("refs/heads/master") is not None

    def test_does_not_delete_local_origin_ref(self, repo: Repository) -> None:
        assert repo.refs.read_ref("refs/remotes/origin/master") is not None


class TestConfiguredUpstreamBranch:
    @pytest.fixture(autouse=True)
    def _setup(
        self,
        create_remote_repo: CreateRemoteRepo,
        legit_cmd: LegitCmd,
        write_commit: WriteCommit,
        legit_path: Path,
    ) -> None:
        self.remote = create_remote_repo("push-remote")

        legit_cmd(
            "remote", "add", "origin", f"file://{cast(Path, self.remote.repo_path)}"
        )
        legit_cmd(
            "config",
            "remote.origin.receivepack",
            f"{legit_path} receive-pack",
        )

        for msg in ("one", "dir/two"):
            write_commit(msg)
        legit_cmd("push", "origin", "master")
        write_commit("three")

        legit_cmd("branch", "--set-upstream-to", "origin/master")

    def test_pushes_current_branch_to_upstream(
        self, legit_cmd: LegitCmd, repo: Repository
    ) -> None:
        cmd, *_, stderr = legit_cmd("push")
        assert_status(cmd, 0)
        new_oid, old_oid = commits(repo, ["master"])[:2]
        expected = (
            f"To file://{cast(Path, self.remote.repo_path)}\n"
            f"   {old_oid}..{new_oid} master -> master\n"
        )
        assert_stderr(stderr, expected)
        assert repo.refs.read_ref(
            "refs/heads/master"
        ) == self.remote.repo.refs.read_ref("refs/heads/master")


class TestMultipleLocalBranches:
    @pytest.fixture(autouse=True)
    def _setup(
        self,
        create_remote_repo: CreateRemoteRepo,
        write_commit: WriteCommit,
        legit_cmd: LegitCmd,
        legit_path: Path,
    ) -> None:
        self.remote = create_remote_repo("push-remote")

        for msg in ("one", "dir/two", "three"):
            write_commit(msg)

        legit_cmd("branch", "topic", "@^")
        legit_cmd("checkout", "topic")
        write_commit("four")

        legit_cmd(
            "remote", "add", "origin", f"file://{cast(Path, self.remote.repo_path)}"
        )
        legit_cmd("config", "remote.origin.receivepack", f"{legit_path} receive-pack")

    def test_displays_new_branches_on_wildcard_push(self, legit_cmd: LegitCmd) -> None:
        cmd, *_, stderr = legit_cmd("push", "origin", "refs/heads/*")
        assert_status(cmd, 0)
        expected = (
            f"To file://{cast(Path, self.remote.repo_path)}\n"
            " * [new branch] master -> master\n"
            " * [new branch] topic -> topic\n"
        )
        assert_stderr(stderr, expected)

    def test_maps_heads_to_heads(self, legit_cmd: LegitCmd, repo: Repository) -> None:
        legit_cmd("push", "origin", "refs/heads/*")
        assert repo.refs.read_ref(
            "refs/heads/master"
        ) == self.remote.repo.refs.read_ref("refs/heads/master")
        assert repo.refs.read_ref("refs/heads/topic") == self.remote.repo.refs.read_ref(
            "refs/heads/topic"
        )

    def test_maps_heads_to_other_namespace(
        self, legit_cmd: LegitCmd, repo: Repository
    ) -> None:
        legit_cmd("push", "origin", "refs/heads/*:refs/other/*")
        assert repo.refs.read_ref(
            "refs/heads/master"
        ) == self.remote.repo.refs.read_ref("refs/other/master")
        assert repo.refs.read_ref("refs/heads/topic") == self.remote.repo.refs.read_ref(
            "refs/other/topic"
        )

    def test_no_other_remote_refs_created(self, legit_cmd: LegitCmd) -> None:
        legit_cmd("push", "origin", "refs/heads/*")
        assert_refs(self.remote.repo, ["HEAD", "refs/heads/master", "refs/heads/topic"])

    def test_sends_all_commits_history(
        self, legit_cmd: LegitCmd, repo: Repository
    ) -> None:
        legit_cmd("push", "origin", "refs/heads/*")
        assert_object_count(cast(Path, self.remote.repo_path), 13)
        local_commits = commits(repo, ["master", "topic"])
        assert local_commits == commits(self.remote.repo, ["master", "topic"])

    def test_checkout_remote_commits_after_push(
        self, legit_cmd: LegitCmd, repo_path: Path
    ) -> None:
        legit_cmd("push", "origin", "refs/heads/*")

        self.remote.legit_cmd(repo_path, "reset", "--hard")

        self.remote.legit_cmd(repo_path, "checkout", "master")
        assert_workspace(
            cast(Path, self.remote.repo_path),
            {
                "one.txt": "one",
                "dir/two.txt": "dir/two",
                "three.txt": "three",
            },
        )

        self.remote.legit_cmd(repo_path, "checkout", "topic")
        assert_workspace(
            cast(Path, self.remote.repo_path),
            {
                "one.txt": "one",
                "dir/two.txt": "dir/two",
                "four.txt": "four",
            },
        )

    def test_push_specific_branch_only(
        self, legit_cmd: LegitCmd, repo: Repository
    ) -> None:
        cmd, *_, stderr = legit_cmd("push", "origin", "refs/heads/*ic:refs/heads/*")
        assert_status(cmd, 0)
        expected = f"To file://{cast(Path, self.remote.repo_path)}\n * [new branch] topic -> top\n"
        assert_stderr(stderr, expected)

        assert_refs(self.remote.repo, ["HEAD", "refs/heads/top"])

        assert_object_count(cast(Path, self.remote.repo_path), 10)

        local_topic_commits = commits(repo, ["topic"])
        assert 3 == len(local_topic_commits)
        assert local_topic_commits == commits(self.remote.repo, [], {"all": True})


class TestReceiverHasStoredPack:
    @pytest.fixture(autouse=True)
    def _setup(
        self,
        create_remote_repo: CreateRemoteRepo,
        legit_cmd: LegitCmd,
        legit_path: Path,
        write_commit: WriteCommit,
        repo_path: Path,
    ) -> None:
        self.alice = create_remote_repo("push-remote-alice")
        self.bob = create_remote_repo("push-remote-bob")

        alice_path = self.alice.path(repo_path)
        bob_path = self.bob.path(repo_path)

        self.alice.legit_cmd(repo_path, "config", "receive.unpackLimit", "5")

        for msg in ("one", "dir/two", "three"):
            write_commit(msg)

        legit_cmd("remote", "add", "alice", f"file://{self.alice.repo_path}")
        legit_cmd(
            "config",
            "remote.alice.receivepack",
            f"{legit_path} receive-pack",
        )

        legit_cmd("push", "alice", "refs/heads/*")

    def test_push_packed_objects_to_another_repo(
        self, legit_path: Path, repo: Repository, repo_path: Path
    ) -> None:
        self.alice.legit_cmd(
            repo_path, "remote", "add", "bob", f"file://{self.bob.repo_path}"
        )
        self.alice.legit_cmd(
            repo_path,
            "config",
            "remote.bob.receivepack",
            f"{legit_path} receive-pack",
        )
        self.alice.legit_cmd(repo_path, "push", "bob", "refs/heads/*")

        assert commits(repo, ["master"]) == commits(self.bob.repo, ["master"])
