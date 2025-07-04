from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Dict

import pytest


@pytest.fixture(autouse=True)
def repo_with_initial_commit(setup_and_teardown, repo_path, commit_all, write_file, base_files, legit_cmd):
    """
    Creates a repository with the base_files committed.
    """
    for path, content in base_files.items():
        write_file(path, content)
    
    commit_all()
    return repo_path


def _snapshot_workspace(repo_path: Path) -> Dict[str, str]:
    """Return a {relative_path: contents} mapping for every *file* in the repo.

    The `.git` directory is purposely ignored.
    """
    result: Dict[str, str] = {}
    for path in repo_path.rglob("*"):
        if ".git" in path.parts or not path.is_file():
            continue
        result[path.relative_to(repo_path).as_posix()] = path.read_text()
    return result


def assert_workspace(repo_path: Path, expected: Dict[str, str]):
    """Assert that the working directory exactly matches *expected*."""
    actual = _snapshot_workspace(repo_path)
    assert actual == expected, f"workspace mismatch – expected {expected}, got {actual}"


def assert_noent(repo_path: Path, name: str):
    """Assert that *name* does not exist inside *repo_path*."""
    assert not (repo_path / name).exists(), f"{name} should not exist in the workspace"


def assert_status(legit_cmd, output: str):
    """Run `status --porcelain` and compare the *verbatim* output."""
    cmd, _stdin, stdout, _stderr = legit_cmd("status", "--porcelain")
    stdout.seek(0)
    assert stdout.read() == output, "status output differs from expectation"


def _check_stderr(stderr_io, expected: str):
    stderr_io.seek(0)
    assert stderr_io.read() == expected, "stderr did not match expectation"


def assert_stale_file(stderr_io, filename: str):
    _check_stderr(
        stderr_io,
        textwrap.dedent(
            f"""error: Your local changes to the following files would be overwritten by checkout:\n\t{filename}\nPlease commit your changes or stash them before you switch branches.\nAborting\n""",
        ),
    )


def assert_stale_directory(stderr_io, filename: str):
    _check_stderr(
        stderr_io,
        textwrap.dedent(
            f"""error: Updating the following directories would lose untracked files in them:\n\t{filename}\n\nAborting\n""",
        ),
    )


def assert_overwrite_conflict(stderr_io, filename: str):
    _check_stderr(
        stderr_io,
        textwrap.dedent(
            f"""error: The following untracked working tree files would be overwritten by checkout:\n\t{filename}\nPlease move or remove them before you switch branches.\nAborting\n""",
        ),
    )


def assert_remove_conflict(stderr_io, filename: str):
    _check_stderr(
        stderr_io,
        textwrap.dedent(
            f"""error: The following untracked working tree files would be removed by checkout:\n\t{filename}\nPlease move or remove them before you switch branches.\nAborting\n""",
        ),
    )

@pytest.fixture
def base_files() -> Dict[str, str]:
    return {
        "1.txt": "1",
        "outer/2.txt": "2",
        "outer/inner/3.txt": "3",
    }


@pytest.fixture
def commit_all(delete, legit_cmd, commit):
    """Stage *everything* (including deletions) and commit a new snapshot."""

    def _commit_all():
        delete(".git/index")  # force the next `add .` to pick up *all* changes
        legit_cmd("add", ".")
        commit("change")

    return _commit_all


@pytest.fixture
def commit_and_checkout(commit_all, legit_cmd):
    """Return a helper that commits *all* then checks out the given revision."""

    def _commit_and_checkout(revision: str):
        commit_all()
        return legit_cmd("checkout", revision)

    return _commit_and_checkout


def test_updates_a_changed_file(write_file, commit_and_checkout, repo_path, base_files, legit_cmd):
    write_file("1.txt", "changed")
    commit_and_checkout("@^")
    assert_workspace(repo_path, base_files)
    assert_status(legit_cmd, "")


def test_fails_to_update_a_modified_file(write_file, commit_all, legit_cmd):
    write_file("1.txt", "changed")
    commit_all()
    write_file("1.txt", "conflict")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_stale_file(stderr, "1.txt")


def test_fails_to_update_a_modified_equal_file(write_file, commit_all, legit_cmd):
    write_file("1.txt", "changed")
    commit_all()
    write_file("1.txt", "1")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_stale_file(stderr, "1.txt")


def test_fails_to_update_a_changed_mode_file(write_file, make_executable, commit_all, legit_cmd):
    write_file("1.txt", "changed")
    commit_all()
    make_executable("1.txt")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_stale_file(stderr, "1.txt")


def test_restores_a_deleted_file(write_file, delete, commit_all, commit_and_checkout, repo_path, base_files, legit_cmd):
    write_file("1.txt", "changed")
    commit_all()
    delete("1.txt")
    legit_cmd("checkout", "@^")
    assert_workspace(repo_path, base_files)
    assert_status(legit_cmd, "")


def test_restores_files_from_a_deleted_directory(write_file, delete, commit_all, commit_and_checkout, repo_path, legit_cmd):
    write_file("outer/inner/3.txt", "changed")
    commit_all()
    delete("outer")
    legit_cmd("checkout", "@^")
    # Only 1.txt and the reverted 3.txt should remain; 2.txt is *missing*.
    assert_workspace(
        repo_path,
        {
            "1.txt": "1",
            "outer/inner/3.txt": "3",
        },
    )
    assert_status(legit_cmd, " D outer/2.txt\n")


def test_fails_to_update_a_staged_file(write_file, commit_all, legit_cmd):
    write_file("1.txt", "changed")
    commit_all()
    write_file("1.txt", "conflict")
    legit_cmd("add", ".")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_stale_file(stderr, "1.txt")


def test_updates_a_staged_equal_file(write_file, commit_all, legit_cmd, repo_path, base_files):
    write_file("1.txt", "changed")
    commit_all()
    write_file("1.txt", "1")
    legit_cmd("add", ".")
    legit_cmd("checkout", "@^")
    assert_workspace(repo_path, base_files)
    assert_status(legit_cmd, "")


def test_fails_to_update_a_staged_changed_mode_file(write_file, make_executable, commit_all, legit_cmd):
    write_file("1.txt", "changed")
    commit_all()
    make_executable("1.txt")
    legit_cmd("add", ".")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_stale_file(stderr, "1.txt")


def test_fails_to_update_an_unindexed_file(write_file, delete, commit_all, legit_cmd):
    write_file("1.txt", "changed")
    commit_all()
    delete("1.txt")
    delete(".git/index")
    legit_cmd("add", ".")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_stale_file(stderr, "1.txt")


def test_fails_to_update_an_unindexed_and_untracked_file(write_file, delete, commit_all, legit_cmd):
    write_file("1.txt", "changed")
    commit_all()
    delete("1.txt")
    delete(".git/index")
    legit_cmd("add", ".")
    write_file("1.txt", "conflict")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_stale_file(stderr, "1.txt")


def test_fails_to_update_an_unindexed_directory(write_file, delete, commit_all, legit_cmd):
    write_file("outer/inner/3.txt", "changed")
    commit_all()
    delete("outer/inner")
    delete(".git/index")
    legit_cmd("add", ".")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_stale_file(stderr, "outer/inner/3.txt")


def test_fails_to_update_with_a_file_at_a_parent_path(write_file, delete, commit_all, legit_cmd):
    write_file("outer/inner/3.txt", "changed")
    commit_all()
    delete("outer/inner")
    write_file("outer/inner", "conflict")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_stale_file(stderr, "outer/inner/3.txt")


def test_fails_to_update_with_a_staged_file_at_a_parent_path(write_file, delete, commit_all, legit_cmd):
    write_file("outer/inner/3.txt", "changed")
    commit_all()
    delete("outer/inner")
    write_file("outer/inner", "conflict")
    legit_cmd("add", ".")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_stale_file(stderr, "outer/inner/3.txt")


def test_fails_to_update_with_an_unstaged_file_at_a_parent_path(write_file, delete, commit_all, legit_cmd):
    write_file("outer/inner/3.txt", "changed")
    commit_all()
    delete("outer/inner")
    delete(".git/index")
    legit_cmd("add", ".")
    write_file("outer/inner", "conflict")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_stale_file(stderr, "outer/inner/3.txt")


def test_fails_to_update_with_a_file_at_a_child_path(write_file, delete, commit_all, legit_cmd):
    write_file("outer/2.txt", "changed")
    commit_all()
    delete("outer/2.txt")
    write_file("outer/2.txt/extra.log", "conflict")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_stale_file(stderr, "outer/2.txt")


def test_fails_to_update_with_a_staged_file_at_a_child_path(write_file, delete, commit_all, legit_cmd):
    write_file("outer/2.txt", "changed")
    commit_all()
    delete("outer/2.txt")
    write_file("outer/2.txt/extra.log", "conflict")
    legit_cmd("add", ".")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_stale_file(stderr, "outer/2.txt")


def test_removes_a_file(write_file, commit_and_checkout, repo_path, base_files, legit_cmd):
    write_file("94.txt", "94")
    commit_and_checkout("@^")
    assert_workspace(repo_path, base_files)
    assert_status(legit_cmd, "")


def test_removes_a_file_from_an_existing_directory(write_file, commit_and_checkout, repo_path, base_files, legit_cmd):
    write_file("outer/94.txt", "94")
    commit_and_checkout("@^")
    assert_workspace(repo_path, base_files)
    assert_status(legit_cmd, "")


def test_removes_a_file_from_a_new_directory(write_file, commit_and_checkout, repo_path, base_files, legit_cmd):
    write_file("new/94.txt", "94")
    commit_and_checkout("@^")
    assert_workspace(repo_path, base_files)
    assert_noent(repo_path, "new")
    assert_status(legit_cmd, "")


def test_removes_a_file_from_a_new_nested_directory(write_file, commit_and_checkout, repo_path, base_files, legit_cmd):
    write_file("new/inner/94.txt", "94")
    commit_and_checkout("@^")
    assert_workspace(repo_path, base_files)
    assert_noent(repo_path, "new")
    assert_status(legit_cmd, "")


def test_removes_a_file_from_a_non_empty_directory(write_file, commit_and_checkout, repo_path, base_files, legit_cmd):
    write_file("outer/94.txt", "94")
    commit_and_checkout("@^")
    assert_workspace(repo_path, base_files)
    assert_status(legit_cmd, "")


def test_fails_to_remove_a_modified_file(write_file, commit_all, legit_cmd):
    write_file("outer/94.txt", "94")
    commit_all()
    write_file("outer/94.txt", "conflict")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_stale_file(stderr, "outer/94.txt")


def test_fails_to_remove_a_changed_mode_file(write_file, make_executable, commit_all, legit_cmd):
    write_file("outer/94.txt", "94")
    commit_all()
    make_executable("outer/94.txt")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_stale_file(stderr, "outer/94.txt")


def test_leaves_a_deleted_file_deleted(write_file, delete, commit_all, legit_cmd, repo_path, base_files):
    write_file("outer/94.txt", "94")
    commit_all()
    delete("outer/94.txt")
    legit_cmd("checkout", "@^")
    assert_workspace(repo_path, base_files)
    assert_status(legit_cmd, "")


def test_leaves_a_deleted_directory_deleted(write_file, delete, commit_all, legit_cmd, repo_path):
    write_file("outer/inner/94.txt", "94")
    commit_all()
    delete("outer/inner")
    legit_cmd("checkout", "@^")
    assert_workspace(
        repo_path,
        {
            "1.txt": "1",
            "outer/2.txt": "2",
        },
    )
    assert_status(legit_cmd, " D outer/inner/3.txt\n")


def test_fails_to_remove_a_staged_file(write_file, commit_all, legit_cmd):
    write_file("outer/94.txt", "94")
    commit_all()
    write_file("outer/94.txt", "conflict")
    legit_cmd("add", ".")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_stale_file(stderr, "outer/94.txt")


def test_fails_to_remove_a_staged_changed_mode_file(write_file, make_executable, commit_all, legit_cmd):
    write_file("outer/94.txt", "94")
    commit_all()
    make_executable("outer/94.txt")
    legit_cmd("add", ".")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_stale_file(stderr, "outer/94.txt")


def test_leaves_an_unindexed_file_deleted(write_file, delete, commit_all, legit_cmd, repo_path, base_files):
    write_file("outer/94.txt", "94")
    commit_all()
    delete("outer/94.txt")
    delete(".git/index")
    legit_cmd("add", ".")
    legit_cmd("checkout", "@^")
    assert_workspace(repo_path, base_files)
    assert_status(legit_cmd, "")


def test_fails_to_remove_an_unindexed_and_untracked_file(write_file, delete, commit_all, legit_cmd):
    write_file("outer/94.txt", "94")
    commit_all()
    delete("outer/94.txt")
    delete(".git/index")
    legit_cmd("add", ".")
    write_file("outer/94.txt", "conflict")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_remove_conflict(stderr, "outer/94.txt")


def test_leaves_an_unindexed_directory_deleted(write_file, delete, commit_all, legit_cmd, repo_path):
    write_file("outer/inner/94.txt", "94")
    commit_all()
    delete("outer/inner")
    delete(".git/index")
    legit_cmd("add", ".")
    legit_cmd("checkout", "@^")
    assert_workspace(
        repo_path,
        {
            "1.txt": "1",
            "outer/2.txt": "2",
        },
    )
    assert_status(legit_cmd, "D  outer/inner/3.txt\n")


def test_fails_to_remove_with_a_file_at_a_parent_path(write_file, delete, commit_all, legit_cmd):
    write_file("outer/inner/94.txt", "94")
    commit_all()
    delete("outer/inner")
    write_file("outer/inner", "conflict")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_stale_file(stderr, "outer/inner/94.txt")


def test_removes_a_file_with_a_staged_file_at_a_parent_path(write_file, delete, commit_all, legit_cmd, repo_path):
    write_file("outer/inner/94.txt", "94")
    commit_all()
    delete("outer/inner")
    write_file("outer/inner", "conflict")
    legit_cmd("add", ".")
    legit_cmd("checkout", "@^")
    assert_workspace(
        repo_path,
        {
            "1.txt": "1",
            "outer/2.txt": "2",
            "outer/inner": "conflict",
        },
    )
    assert_status(legit_cmd, "A  outer/inner\nD  outer/inner/3.txt\n")


def test_fails_to_remove_with_an_unstaged_file_at_a_parent_path(write_file, delete, commit_all, legit_cmd):
    write_file("outer/inner/94.txt", "94")
    commit_all()
    delete("outer/inner")
    delete(".git/index")
    legit_cmd("add", ".")
    write_file("outer/inner", "conflict")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_remove_conflict(stderr, "outer/inner")


def test_fails_to_remove_with_a_file_at_a_child_path(write_file, delete, commit_all, legit_cmd):
    write_file("outer/94.txt", "94")
    commit_all()
    delete("outer/94.txt")
    write_file("outer/94.txt/extra.log", "conflict")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_stale_file(stderr, "outer/94.txt")


def test_removes_a_file_with_a_staged_file_at_a_child_path(write_file, delete, commit_all, legit_cmd, repo_path, base_files):
    write_file("outer/94.txt", "94")
    commit_all()
    delete("outer/94.txt")
    write_file("outer/94.txt/extra.log", "conflict")
    legit_cmd("add", ".")
    legit_cmd("checkout", "@^")
    assert_workspace(repo_path, base_files)
    assert_status(legit_cmd, "")


def test_adds_a_file(delete, commit_and_checkout, repo_path, base_files, legit_cmd):
    delete("1.txt")
    commit_and_checkout("@^")
    assert_workspace(repo_path, base_files)
    assert_status(legit_cmd, "")


def test_adds_a_file_to_a_directory(delete, commit_and_checkout, repo_path, base_files, legit_cmd):
    delete("outer/2.txt")
    commit_and_checkout("@^")
    assert_workspace(repo_path, base_files)
    assert_status(legit_cmd, "")


def test_adds_a_directory(delete, commit_and_checkout, repo_path, base_files, legit_cmd):
    delete("outer")
    commit_and_checkout("@^")
    assert_workspace(repo_path, base_files)
    assert_status(legit_cmd, "")


def test_fails_to_add_an_untracked_file(delete, write_file, commit_all, legit_cmd):
    delete("outer/2.txt")
    commit_all()
    write_file("outer/2.txt", "conflict")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_overwrite_conflict(stderr, "outer/2.txt")


def test_fails_to_add_an_added_file(delete, write_file, commit_all, legit_cmd):
    delete("outer/2.txt")
    commit_all()
    write_file("outer/2.txt", "conflict")
    legit_cmd("add", ".")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_stale_file(stderr, "outer/2.txt")


def test_adds_a_staged_equal_file(delete, write_file, commit_all, legit_cmd, repo_path, base_files):
    delete("outer/2.txt")
    commit_all()
    write_file("outer/2.txt", "2")
    legit_cmd("add", ".")
    legit_cmd("checkout", "@^")
    assert_workspace(repo_path, base_files)
    assert_status(legit_cmd, "")


def test_fails_to_add_with_an_untracked_file_at_a_parent_path(delete, write_file, commit_all, legit_cmd):
    delete("outer/inner/3.txt")
    commit_all()
    delete("outer/inner")
    write_file("outer/inner", "conflict")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_overwrite_conflict(stderr, "outer/inner")


def test_adds_a_file_with_an_added_file_at_a_parent_path(delete, write_file, commit_all, legit_cmd, repo_path, base_files):
    delete("outer/inner/3.txt")
    commit_all()
    delete("outer/inner")
    write_file("outer/inner", "conflict")
    legit_cmd("add", ".")
    legit_cmd("checkout", "@^")
    assert_workspace(repo_path, base_files)
    assert_status(legit_cmd, "")


def test_fails_to_add_with_an_untracked_file_at_a_child_path(delete, write_file, commit_all, legit_cmd):
    delete("outer/2.txt")
    commit_all()
    write_file("outer/2.txt/extra.log", "conflict")
    _cmd, _stdin, _stdout, stderr = legit_cmd("checkout", "@^")
    assert_stale_directory(stderr, "outer/2.txt")


def test_adds_a_file_with_an_added_file_at_a_child_path(delete, write_file, commit_all, legit_cmd, repo_path, base_files):
    delete("outer/2.txt")
    commit_all()
    write_file("outer/2.txt/extra.log", "conflict")
    legit_cmd("add", ".")
    legit_cmd("checkout", "@^")
    assert_workspace(repo_path, base_files)
    assert_status(legit_cmd, "")


def test_replaces_a_file_with_a_directory(delete, write_file, commit_and_checkout, repo_path, base_files, legit_cmd):
    delete("outer/inner")
    write_file("outer/inner", "in")
    commit_and_checkout("@^")
    assert_workspace(repo_path, base_files)
    assert_status(legit_cmd, "")


def test_replaces_a_directory_with_a_file(delete, write_file, commit_and_checkout, repo_path, base_files, legit_cmd):
    delete("outer/2.txt")
    write_file("outer/2.txt/nested.log", "nested")
    commit_and_checkout("@^")
    assert_workspace(repo_path, base_files)
    assert_status(legit_cmd, "")


def test_maintains_workspace_modifications(write_file, delete, commit_all, legit_cmd, repo_path):
    write_file("1.txt", "changed")
    commit_all()
    write_file("outer/2.txt", "hello")
    delete("outer/inner")
    legit_cmd("checkout", "@^")
    assert_workspace(
        repo_path,
        {
            "1.txt": "1",
            "outer/2.txt": "hello",
        },
    )
    assert_status(legit_cmd, " M outer/2.txt\n D outer/inner/3.txt\n")


def test_maintains_index_modifications(write_file, commit_all, legit_cmd, repo_path, base_files):
    write_file("1.txt", "changed")
    commit_all()
    write_file("outer/2.txt", "hello")
    write_file("outer/inner/4.txt", "world")
    legit_cmd("add", ".")
    legit_cmd("checkout", "@^")
    expected = base_files.copy()
    expected.update({"outer/2.txt": "hello", "outer/inner/4.txt": "world"})
    assert_workspace(repo_path, expected)
    assert_status(legit_cmd, "M  outer/2.txt\nA  outer/inner/4.txt\n")

@pytest.fixture
def repo_with_chain(setup_and_teardown, repo, write_file, commit, legit_cmd):
    # Create a chain of three commits: “first”, “second”, “third”
    for msg in ["first", "second", "third"]:
        write_file("file.txt", msg)
        legit_cmd("add", ".")
        commit(msg)
    # Create branches “topic” at HEAD (third) and “second” at HEAD^ (second)
    legit_cmd("branch", "topic")
    legit_cmd("branch", "second", "@^")
    return repo

def test_links_HEAD_to_branch(repo_with_chain, legit_cmd, repo):
    legit_cmd("checkout", "topic")
    assert repo.refs.current_ref().path == "refs/heads/topic"

def test_resolves_HEAD_to_same_object_as_branch(repo_with_chain, legit_cmd, repo):
    legit_cmd("checkout", "topic")
    assert repo.refs.read_ref("topic") == repo.refs.read_head()

def test_prints_message_when_switching_to_same_branch(repo_with_chain, legit_cmd):
    legit_cmd("checkout", "topic")
    _, _stdin, _stdout, stderr = legit_cmd("checkout", "topic")
    stderr.seek(0)
    assert stderr.read() == "Already on 'topic'\n"

def test_prints_message_when_switching_to_another_branch(repo_with_chain, legit_cmd):
    legit_cmd("checkout", "topic")
    _, _stdin, _stdout, stderr = legit_cmd("checkout", "second")
    stderr.seek(0)
    assert stderr.read() == "Switched to branch 'second'\n"

def test_prints_warning_when_detaching_HEAD(repo_with_chain, legit_cmd, repo):
    legit_cmd("checkout", "topic")
    _, _stdin, _stdout, stderr = legit_cmd("checkout", "@")
    stderr.seek(0)
    short = repo.database.short_oid(repo.refs.read_head())
    expected = textwrap.dedent(f"""\
        Note: checking out '@'.

        You are in 'detached HEAD' state. You can look around, make experimental
        changes and commit them, and you can discard any commits you make in this
        state without impacting any branches by performing another checkout.

        If you want to create a new branch to retain commits you create, you may
        do so (now or later) by using the branch command. Example:

            legit branch <new-branch-name>

        HEAD is now at {short} third
        """)
    assert stderr.read() == expected

def test_detaches_HEAD_on_relative_revision(repo_with_chain, legit_cmd, repo):
    _, _stdin, _stdout, stderr = legit_cmd("checkout", "topic^")
    assert repo.refs.current_ref().path == "HEAD"

def test_puts_revision_value_in_HEAD(repo_with_chain, legit_cmd, repo):
    _, _stdin, _stdout, stderr = legit_cmd("checkout", "topic^")
    # “topic^” resolves to the second commit
    from legit.revision import Revision
    expected_oid = Revision(repo, "topic^").resolve()
    assert repo.refs.read_head() == expected_oid

def test_prints_message_when_switching_to_same_commit(repo_with_chain, legit_cmd, repo):
    legit_cmd("checkout", "topic^")
    short = repo.database.short_oid(repo.refs.read_head())
    _, _stdin, _stdout, stderr = legit_cmd("checkout", "@")
    stderr.seek(0)
    assert stderr.read() == f"HEAD is now at {short} second\n"

def test_prints_message_when_switching_to_different_commit(repo_with_chain, legit_cmd, repo):
    # first go to topic^ (second), then back to topic^^ (first)
    legit_cmd("checkout", "topic^")
    a = repo.database.short_oid(repo.refs.read_head())
    _, _stdin, _stdout, stderr = legit_cmd("checkout", "topic^^")
    b = repo.database.short_oid(repo.refs.read_head())
    stderr.seek(0)
    assert stderr.read() == textwrap.dedent(f"""\
        Previous HEAD position was {a} second
        HEAD is now at {b} first
        """)

def test_prints_message_when_switching_to_branch_with_same_ID(repo_with_chain, legit_cmd, repo):
    # from a detached HEAD at the second commit, checkout “second” branch which points there
    legit_cmd("checkout", "topic^")
    _, _stdin, _stdout, stderr = legit_cmd("checkout", "second")
    stderr.seek(0)
    assert stderr.read() == "Switched to branch 'second'\n"

def test_prints_message_when_switching_to_branch_from_detached(repo_with_chain, legit_cmd, repo):
    legit_cmd("checkout", "topic^")
    short = repo.database.short_oid(repo.refs.read_head())
    _, _stdin, _stdout, stderr = legit_cmd("checkout", "topic")
    stderr.seek(0)
    assert stderr.read() == textwrap.dedent(f"""\
        Previous HEAD position was {short} second
        Switched to branch 'topic'
        """)
