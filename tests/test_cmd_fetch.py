import re
import tempfile
import shutil
from pathlib import Path
from io import BytesIO, StringIO, TextIOBase

import pytest

from legit.command import Command
from legit.repository import Repository
from legit.rev_list import RevList
from tests.cmd_helpers import (
    assert_status,
    assert_stderr,
    assert_workspace,
    CapturedStderr,
)
from tests.remote_repo import RemoteRepo


def commits(repo: Repository, revs: list[str], options: dict | None = None):
    if options is None:
        options = {}
    return [
        repo.database.short_oid(commit.oid)
        for commit, _ in RevList(repo, revs, options).each()
    ]


def assert_object_count(repo_root: Path, expected: int):
    count = sum(1 for p in (repo_root / ".git" / "objects").rglob("*") if p.is_file())
    assert count == expected, (
        f"object-count mismatch – expected {expected}, found {count}"
    )


@pytest.fixture
def legit_path():
    return Path(shutil.which("legit") or "legit")


@pytest.fixture
def remote_single_branch(repo_path, legit_cmd, legit_path):
    remote = RemoteRepo("fetch-remote")
    remote_repo_path = remote.path(repo_path)

    remote.legit_cmd(repo_path, "init", str(remote_repo_path))

    remote.legit_cmd(repo_path, "config", "user.name", "Remote Tester")
    remote.legit_cmd(repo_path, "config", "user.email", "remote@example.com")

    def _write_commit(msg):
        nonlocal remote

        remote.write_file(repo_path, f"{msg}.txt", msg)
        remote.legit_cmd(repo_path, "add", ".")
        remote.legit_cmd(
            repo_path,
            "commit",
            "-m",
            msg,
            env={
                "GIT_AUTHOR_NAME": "Remote A. U. Thor",
                "GIT_AUTHOR_EMAIL": "remote@example.com",
            },
        )

    for msg in ("one", "dir/two", "three"):
        _write_commit(msg)

    legit_cmd("remote", "add", "origin", f"file://{remote_repo_path}")
    legit_cmd("config", "remote.origin.uploadpack", f"{legit_path} upload-pack")
    return remote


@pytest.fixture
def remote_multiple_branches(legit_cmd, legit_path, repo_path):
    remote = RemoteRepo("fetch-remote")
    remote.legit_cmd(repo_path, "init", str(remote.path(repo_path)))

    def _write_commit(msg):
        nonlocal remote

        remote.write_file(repo_path, f"{msg}.txt", msg)
        remote.legit_cmd(repo_path, "add", ".")
        remote.legit_cmd(repo_path, "commit", "-m", msg)

    for msg in ("one", "dir/two", "three"):
        _write_commit(msg)

    remote.legit_cmd(repo_path, "branch", "topic", "@^")
    remote.legit_cmd(repo_path, "checkout", "topic")
    _write_commit("four")

    legit_cmd("remote", "add", "origin", f"file://{remote.path(repo_path)}")
    legit_cmd("config", "remote.origin.uploadpack", f"{legit_path} upload-pack")
    return remote


def test_fetch_displays_new_branch(remote_single_branch, legit_cmd, repo_path):
    remote = remote_single_branch
    cmd, stdin, stdout, stderr = legit_cmd("fetch")

    assert_status(cmd, 0)
    assert_stderr(
        stderr,
        f"From file://{remote.path(repo_path)}\n"
        " * [new branch] master -> origin/master\n",
    )


def test_fetch_maps_remote_head_to_local(remote_single_branch, legit_cmd, repo):
    legit_cmd("fetch")
    assert remote_single_branch.repo.refs.read_ref(
        "refs/heads/master"
    ) == repo.refs.read_ref("refs/remotes/origin/master")


def test_fetch_maps_remote_head_to_alternate_ref(remote_single_branch, legit_cmd, repo):
    legit_cmd("fetch", "origin", "refs/heads/*:refs/remotes/other/prefix-*")
    assert remote_single_branch.repo.refs.read_ref(
        "refs/heads/master"
    ) == repo.refs.read_ref("refs/remotes/other/prefix-master")


def test_fetch_shorthand_refs(remote_single_branch, legit_cmd, repo):
    legit_cmd("fetch", "origin", "master:topic")
    assert remote_single_branch.repo.refs.read_ref(
        "refs/heads/master"
    ) == repo.refs.read_ref("refs/heads/topic")


def test_fetch_shorthand_head_refs(remote_single_branch, legit_cmd, repo):
    legit_cmd("fetch", "origin", "master:heads/topic")
    assert remote_single_branch.repo.refs.read_ref(
        "refs/heads/master"
    ) == repo.refs.read_ref("refs/heads/topic")


def test_fetch_shorthand_remote_refs(remote_single_branch, legit_cmd, repo):
    legit_cmd("fetch", "origin", "master:remotes/topic")
    assert remote_single_branch.repo.refs.read_ref(
        "refs/heads/master"
    ) == repo.refs.read_ref("refs/remotes/topic")


def test_fetch_does_not_create_other_refs(remote_single_branch, legit_cmd, repo):
    legit_cmd("fetch")
    assert sorted(r.path for r in repo.refs.list_all_refs()) == [
        "HEAD",
        "refs/remotes/origin/master",
    ]


def test_fetch_retrieves_all_commits(remote_single_branch, legit_cmd, repo):
    legit_cmd("fetch")
    assert commits(remote_single_branch.repo, ["master"]) == commits(
        repo, ["origin/master"]
    )


def test_fetch_can_checkout_remote_commits(remote_single_branch, legit_cmd, repo_path):
    legit_cmd("fetch")

    legit_cmd("checkout", "origin/master^")
    assert_workspace(repo_path, {"one.txt": "one", "dir/two.txt": "dir/two"})

    legit_cmd("checkout", "origin/master")
    assert_workspace(
        repo_path,
        {"one.txt": "one", "dir/two.txt": "dir/two", "three.txt": "three"},
    )

    legit_cmd("checkout", "origin/master^^")
    assert_workspace(repo_path, {"one.txt": "one"})


# ---------------------------------------------------------------------- #
# unpack-limit behaviour
# ---------------------------------------------------------------------- #


def test_fetch_unpack_limit_keeps_pack(remote_single_branch, legit_cmd, repo_path):
    legit_cmd("config", "fetch.unpackLimit", "5")
    legit_cmd("fetch")
    assert_object_count(repo_path, 2)


def test_fetch_unpack_limit_commits_loadable(remote_single_branch, legit_cmd, repo):
    legit_cmd("config", "fetch.unpackLimit", "5")
    legit_cmd("fetch")

    pack_dir = repo.git_path / "objects" / "pack"

    repo.database.backend.stores = [
        repo.database.backend.loose
    ] + repo.database.backend.packed()

    import os

    print(f"Checking pack_dir contents after fetch: {pack_dir}")
    print(f"os.listdir(pack_dir) = {os.listdir(pack_dir)}")

    remote_commits = commits(remote_single_branch.repo, ["master"])
    local_tracking_commits = commits(repo, ["origin/master"])

    print(f"Remote master commits: {remote_commits}")
    print(f"Local origin/master commits: {local_tracking_commits}")
    assert commits(remote_single_branch.repo, ["master"]) == commits(
        repo, ["origin/master"]
    )


# ---------------------------------------------------------------------- #
# remote ahead
# ---------------------------------------------------------------------- #


def test_fetch_remote_ahead_fast_forward(
    remote_single_branch, legit_cmd, repo, repo_path
):
    legit_cmd("fetch")
    local_head = commits(repo, ["origin/master"])[0]

    remote_single_branch.write_file("one.txt", "changed")
    remote_single_branch.legit_cmd(repo_path, "add", ".")
    remote_single_branch.legit_cmd(
        repo_path,
        "commit",
        "-m",
        "changed",
        env={
            "GIT_AUTHOR_NAME": "Remote A. U. Thor",
            "GIT_AUTHOR_EMAIL": "remote@example.com",
        },
    )
    remote_head = commits(remote_single_branch.repo, ["master"])[0]

    cmd, _, _, stderr = legit_cmd("fetch")
    assert_status(cmd, 0)
    assert_stderr(
        stderr,
        f"From file://{remote_single_branch.repo_path}\n"
        f"   {local_head}..{remote_head} master -> origin/master\n",
    )


# ---------------------------------------------------------------------- #
# remote diverged
# ---------------------------------------------------------------------- #


@pytest.fixture
def diverged_setup(remote_single_branch, legit_cmd, repo, repo_path):
    legit_cmd("fetch")

    remote_single_branch.write_file("one.txt", "changed")
    remote_single_branch.legit_cmd(repo_path, "add", ".")
    remote_single_branch.legit_cmd(
        repo_path,
        "commit",
        "--amend",
        env={
            "GIT_AUTHOR_NAME": "Remote A. U. Thor",
            "GIT_AUTHOR_EMAIL": "remote@example.com",
        },
    )

    local_head = commits(repo, ["origin/master"])[0]
    remote_head = commits(remote_single_branch.repo, ["master"])[0]
    return remote_single_branch, local_head, remote_head


def test_fetch_diverged_forced_update_message(diverged_setup, legit_cmd):
    remote, local_head, remote_head = diverged_setup
    cmd, _, _, stderr = legit_cmd("fetch")
    assert_status(cmd, 0)
    assert_stderr(
        stderr,
        f"From file://{remote.repo_path}\n"
        f" + {local_head}...{remote_head} master -> origin/master (forced update)\n",
    )


def test_fetch_diverged_forced_option_message(diverged_setup, legit_cmd):
    remote, local_head, remote_head = diverged_setup
    cmd, _, _, stderr = legit_cmd(
        "fetch", "-f", "origin", "refs/heads/*:refs/remotes/origin/*"
    )
    assert_status(cmd, 0)
    assert_stderr(
        stderr,
        f"From file://{remote.repo_path}\n"
        f" + {local_head}...{remote_head} master -> origin/master (forced update)\n",
    )


def test_fetch_diverged_updates_local_ref(diverged_setup, legit_cmd, repo):
    _, _, remote_head = diverged_setup
    legit_cmd("fetch")
    assert remote_head == commits(repo, ["origin/master"])[0]


@pytest.fixture
def diverged_not_forced_setup(diverged_setup, legit_cmd):
    remote, local_head, remote_head = diverged_setup
    cmd, _, _, stderr = legit_cmd(
        "fetch", "origin", "refs/heads/*:refs/remotes/origin/*"
    )
    return remote, local_head, remote_head, cmd, stderr


def test_fetch_diverged_not_forced_status(diverged_not_forced_setup):
    _, _, _, cmd, _ = diverged_not_forced_setup
    assert_status(cmd, 1)


def test_fetch_diverged_not_forced_message(diverged_not_forced_setup):
    remote, local_head, _, _, stderr = diverged_not_forced_setup
    assert_stderr(
        stderr,
        f"From file://{remote.repo_path}\n"
        f" ! [rejected] master -> origin/master (non-fast-forward)\n",
    )


def test_fetch_diverged_not_forced_ref_unchanged(diverged_not_forced_setup, repo):
    _, local_head, _, _, _ = diverged_not_forced_setup
    assert local_head == commits(repo, ["origin/master"])[0]


# ---------------------------------------------------------------------- #
# multiple-branch remote
# ---------------------------------------------------------------------- #


def test_fetch_multiple_displays_new_branches(remote_multiple_branches, legit_cmd):
    remote = remote_multiple_branches
    cmd, _, _, stderr = legit_cmd("fetch")
    assert_status(cmd, 0)
    assert_stderr(
        stderr,
        f"From file://{remote.repo_path}\n"
        " * [new branch] master -> origin/master\n"
        " * [new branch] topic -> origin/topic\n",
    )


def test_fetch_multiple_maps_heads(remote_multiple_branches, legit_cmd, repo):
    legit_cmd("fetch")
    assert remote_multiple_branches.repo.refs.read_ref(
        "refs/heads/master"
    ) == repo.refs.read_ref("refs/remotes/origin/master")
    assert remote_multiple_branches.repo.refs.read_ref(
        "refs/heads/topic"
    ) == repo.refs.read_ref("refs/remotes/origin/topic")


def test_fetch_multiple_maps_to_other_ref(remote_multiple_branches, legit_cmd, repo):
    legit_cmd("fetch", "origin", "refs/heads/*:refs/remotes/other/prefix-*")
    assert remote_multiple_branches.repo.refs.read_ref(
        "refs/heads/master"
    ) == repo.refs.read_ref("refs/remotes/other/prefix-master")
    assert remote_multiple_branches.repo.refs.read_ref(
        "refs/heads/topic"
    ) == repo.refs.read_ref("refs/remotes/other/prefix-topic")


def test_fetch_multiple_no_extra_refs(remote_multiple_branches, legit_cmd, repo):
    legit_cmd("fetch")
    assert sorted(r.path for r in repo.refs.list_all_refs()) == [
        "HEAD",
        "refs/remotes/origin/master",
        "refs/remotes/origin/topic",
    ]


def test_fetch_multiple_retrieves_all_commits(
    remote_multiple_branches, legit_cmd, repo, repo_path
):
    legit_cmd("fetch")
    assert_object_count(repo_path, 13)

    remote_commits = commits(remote_multiple_branches.repo, [], {"all": True})
    assert len(remote_commits) == 4
    assert remote_commits == commits(repo, [], {"all": True})


def test_fetch_multiple_checkout_commits(
    remote_multiple_branches, legit_cmd, repo_path
):
    legit_cmd("fetch")

    legit_cmd("checkout", "origin/master")
    assert_workspace(
        repo_path,
        {"one.txt": "one", "dir/two.txt": "dir/two", "three.txt": "three"},
    )

    legit_cmd("checkout", "origin/topic")
    assert_workspace(
        repo_path,
        {"one.txt": "one", "dir/two.txt": "dir/two", "four.txt": "four"},
    )


# ---------------------------------------------------------------------- #
# specific-branch fetch
# ---------------------------------------------------------------------- #


@pytest.fixture
def specific_branch_setup(remote_multiple_branches, legit_cmd, repo_path):
    remote = remote_multiple_branches
    cmd, _, _, stderr = legit_cmd(
        "fetch", "origin", "+refs/heads/*ic:refs/remotes/origin/*"
    )
    return remote, cmd, stderr, repo_path


def test_fetch_specific_branch_message(specific_branch_setup):
    remote, _, stderr, _ = specific_branch_setup
    assert_stderr(
        stderr,
        f"From file://{remote.repo_path}\n * [new branch] topic -> origin/top\n",
    )


def test_fetch_specific_branch_no_extra_refs(specific_branch_setup, repo):
    assert sorted(r.path for r in repo.refs.list_all_refs()) == [
        "HEAD",
        "refs/remotes/origin/top",
    ]


def test_fetch_specific_branch_retrieves_only_topic(specific_branch_setup, repo):
    remote, _, _, repo_path = specific_branch_setup
    assert_object_count(repo_path, 10)

    remote_commits = commits(remote.repo, ["topic"])
    assert len(remote_commits) == 3
    assert remote_commits == commits(repo, [], {"all": True})
