import textwrap
from os import linesep
from pathlib import Path
from typing import Callable, TypeAlias, cast

import pytest

from legit.repository import Repository
from tests.cmd_helpers import (
    CapturedStderr,
    assert_noent,
    assert_stderr,
    assert_stdout,
    assert_workspace,
)
from tests.conftest import (
    Commit,
    Delete,
    LegitCmd,
    LegitCmdResult,
    MakeExecutable,
    ResolveRevision,
    WriteFile,
)

CommitAll: TypeAlias = Callable[[], None]
CommitAndCheckout: TypeAlias = Callable[[str], LegitCmdResult]


@pytest.fixture
def commit_all(delete: Delete, legit_cmd: LegitCmd, commit: Commit) -> CommitAll:
    def _commit_all() -> None:
        delete(".git/index")
        legit_cmd("add", ".")
        commit("change")

    return _commit_all


@pytest.fixture
def commit_and_checkout(
    commit_all: CommitAll, legit_cmd: LegitCmd
) -> CommitAndCheckout:
    def _commit_and_checkout(revision: str) -> LegitCmdResult:
        commit_all()
        return legit_cmd("checkout", revision)

    return _commit_and_checkout


def assert_stale_file(stderr: CapturedStderr, filename: str) -> None:
    assert_stderr(
        stderr,
        textwrap.dedent(
            f"""\
            error: Your local changes to the following files would be overwritten by checkout:
            \t{filename}
            Please commit your changes or stash them before you switch branches.
            Aborting
            """,
        ),
    )


def assert_stale_directory(stderr: CapturedStderr, filename: str) -> None:
    assert_stderr(
        stderr,
        textwrap.dedent(
            f"""\
            error: Updating the following directories would lose untracked files in them:
            \t{filename}
            
            Aborting
            """,
        ),
    )


def assert_overwrite_conflict(stderr: CapturedStderr, filename: str) -> None:
    assert_stderr(
        stderr,
        textwrap.dedent(
            f"""\
            error: The following untracked working tree files would be overwritten by checkout:
            \t{filename}
            Please move or remove them before you switch branches.
            Aborting
            """,
        ),
    )


def assert_remove_conflict(stderr: CapturedStderr, filename: str) -> None:
    assert_stderr(
        stderr,
        textwrap.dedent(
            f"""\
            error: The following untracked working tree files would be removed by checkout:
            \t{filename}
            Please move or remove them before you switch branches.
            Aborting
            """,
        ),
    )


def assert_status(legit_cmd: LegitCmd, expected: str) -> None:
    *_, stdout, _ = legit_cmd("status", "--porcelain")
    assert_stdout(stdout, expected)


@pytest.fixture
def base_files() -> dict[str, str]:
    return {
        "1.txt": "1",
        "outer/2.txt": "2",
        "outer/inner/3.txt": "3",
    }


class TestCheckout:
    @pytest.fixture(autouse=True)
    def setup(
        self, commit_all: CommitAll, write_file: WriteFile, base_files: dict[str, str]
    ) -> None:
        for path, content in base_files.items():
            write_file(path, content)

        commit_all()

    def test_it_updates_a_changed_file(
        self,
        write_file: WriteFile,
        commit_and_checkout: CommitAndCheckout,
        repo_path: Path,
        base_files: dict[str, str],
        legit_cmd: LegitCmd,
    ) -> None:
        write_file("1.txt", "changed")
        commit_and_checkout("@^")

        assert_workspace(repo_path, base_files)
        assert_status(legit_cmd, "")

    def test_it_fails_to_update_a_modified_file(
        self, write_file: WriteFile, commit_all: CommitAll, legit_cmd: LegitCmd
    ) -> None:
        write_file("1.txt", "changed")
        commit_all()

        write_file("1.txt", "conflict")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_stale_file(stderr, "1.txt")

    def test_it_fails_to_update_a_modified_equal_file(
        self, write_file: WriteFile, commit_all: CommitAll, legit_cmd: LegitCmd
    ) -> None:
        write_file("1.txt", "changed")
        commit_all()

        write_file("1.txt", "1")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_stale_file(stderr, "1.txt")

    def test_it_fails_to_update_a_changed_mode_file(
        self,
        write_file: WriteFile,
        make_executable: MakeExecutable,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
    ) -> None:
        write_file("1.txt", "changed")
        commit_all()

        make_executable("1.txt")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_stale_file(stderr, "1.txt")

    def test_it_restores_a_deleted_file(
        self,
        write_file: WriteFile,
        delete: Delete,
        commit_all: CommitAll,
        repo_path: Path,
        base_files: dict[str, str],
        legit_cmd: LegitCmd,
    ) -> None:
        write_file("1.txt", "changed")
        commit_all()

        delete("1.txt")
        legit_cmd("checkout", "@^")

        assert_workspace(repo_path, base_files)
        assert_status(legit_cmd, "")

    def test_it_restores_files_from_a_deleted_directory(
        self,
        write_file: WriteFile,
        delete: Delete,
        commit_all: CommitAll,
        repo_path: Path,
        legit_cmd: LegitCmd,
    ) -> None:
        write_file("outer/inner/3.txt", "changed")
        commit_all()

        delete("outer")
        legit_cmd("checkout", "@^")

        assert_workspace(
            repo_path,
            {
                "1.txt": "1",
                "outer/inner/3.txt": "3",
            },
        )
        assert_status(legit_cmd, " D outer/2.txt\n")

    def test_it_fails_to_update_a_staged_file(
        self, write_file: WriteFile, commit_all: CommitAll, legit_cmd: LegitCmd
    ) -> None:
        write_file("1.txt", "changed")
        commit_all()

        write_file("1.txt", "conflict")
        legit_cmd("add", ".")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_stale_file(stderr, "1.txt")

    def test_it_updates_a_staged_equal_file(
        self,
        write_file: WriteFile,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
        repo_path: Path,
        base_files: dict[str, str],
    ) -> None:
        write_file("1.txt", "changed")
        commit_all()

        write_file("1.txt", "1")
        legit_cmd("add", ".")
        legit_cmd("checkout", "@^")

        assert_workspace(repo_path, base_files)
        assert_status(legit_cmd, "")

    def test_it_fails_to_update_a_staged_changed_mode_file(
        self,
        write_file: WriteFile,
        make_executable: MakeExecutable,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
    ) -> None:
        write_file("1.txt", "changed")
        commit_all()

        make_executable("1.txt")
        legit_cmd("add", ".")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_stale_file(stderr, "1.txt")

    def test_it_fails_to_update_an_unindexed_file(
        self,
        write_file: WriteFile,
        delete: Delete,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
    ) -> None:
        write_file("1.txt", "changed")
        commit_all()

        delete("1.txt")
        delete(".git/index")
        legit_cmd("add", ".")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_stale_file(stderr, "1.txt")

    def test_it_fails_to_update_an_unindexed_and_untracked_file(
        self,
        write_file: WriteFile,
        delete: Delete,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
    ) -> None:
        write_file("1.txt", "changed")
        commit_all()

        delete("1.txt")
        delete(".git/index")
        legit_cmd("add", ".")
        write_file("1.txt", "conflict")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_stale_file(stderr, "1.txt")

    def test_it_fails_to_update_an_unindexed_directory(
        self,
        write_file: WriteFile,
        delete: Delete,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
    ) -> None:
        write_file("outer/inner/3.txt", "changed")
        commit_all()

        delete("outer/inner")
        delete(".git/index")
        legit_cmd("add", ".")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_stale_file(stderr, "outer/inner/3.txt")

    def test_it_fails_to_update_with_a_file_at_a_parent_path(
        self,
        write_file: WriteFile,
        delete: Delete,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
    ) -> None:
        write_file("outer/inner/3.txt", "changed")
        commit_all()

        delete("outer/inner")
        write_file("outer/inner", "conflict")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_stale_file(stderr, "outer/inner/3.txt")

    def test_it_fails_to_update_with_a_staged_file_at_a_parent_path(
        self,
        write_file: WriteFile,
        delete: Delete,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
    ) -> None:
        write_file("outer/inner/3.txt", "changed")
        commit_all()

        delete("outer/inner")
        write_file("outer/inner", "conflict")
        legit_cmd("add", ".")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_stale_file(stderr, "outer/inner/3.txt")

    def test_it_fails_to_update_with_an_unstaged_file_at_a_parent_path(
        self,
        write_file: WriteFile,
        delete: Delete,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
    ) -> None:
        write_file("outer/inner/3.txt", "changed")
        commit_all()

        delete("outer/inner")
        delete(".git/index")
        legit_cmd("add", ".")
        write_file("outer/inner", "conflict")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_stale_file(stderr, "outer/inner/3.txt")

    def test_it_fails_to_update_with_a_file_at_a_child_path(
        self,
        write_file: WriteFile,
        delete: Delete,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
    ) -> None:
        write_file("outer/2.txt", "changed")
        commit_all()

        delete("outer/2.txt")
        write_file("outer/2.txt/extra.log", "conflict")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_stale_file(stderr, "outer/2.txt")

    def test_it_fails_to_update_with_a_staged_file_at_a_child_path(
        self,
        write_file: WriteFile,
        delete: Delete,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
    ) -> None:
        write_file("outer/2.txt", "changed")
        commit_all()

        delete("outer/2.txt")
        write_file("outer/2.txt/extra.log", "conflict")
        legit_cmd("add", ".")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_stale_file(stderr, "outer/2.txt")

    def test_it_removes_a_file(
        self,
        write_file: WriteFile,
        commit_and_checkout: CommitAndCheckout,
        repo_path: Path,
        base_files: dict[str, str],
        legit_cmd: LegitCmd,
    ) -> None:
        write_file("94.txt", "94")
        commit_and_checkout("@^")

        assert_workspace(repo_path, base_files)
        assert_status(legit_cmd, "")

    def test_it_removes_a_file_from_an_existing_directory(
        self,
        write_file: WriteFile,
        commit_and_checkout: CommitAndCheckout,
        repo_path: Path,
        base_files: dict[str, str],
        legit_cmd: LegitCmd,
    ) -> None:
        write_file("outer/94.txt", "94")
        commit_and_checkout("@^")

        assert_workspace(repo_path, base_files)
        assert_status(legit_cmd, "")

    def test_it_removes_a_file_from_a_new_directory(
        self,
        write_file: WriteFile,
        commit_and_checkout: CommitAndCheckout,
        repo_path: Path,
        base_files: dict[str, str],
        legit_cmd: LegitCmd,
    ) -> None:
        write_file("new/94.txt", "94")
        commit_and_checkout("@^")

        assert_workspace(repo_path, base_files)
        assert_noent(repo_path, "new")
        assert_status(legit_cmd, "")

    def test_it_removes_a_file_from_a_new_nested_directory(
        self,
        write_file: WriteFile,
        commit_and_checkout: CommitAndCheckout,
        repo_path: Path,
        base_files: dict[str, str],
        legit_cmd: LegitCmd,
    ) -> None:
        write_file("new/inner/94.txt", "94")
        commit_and_checkout("@^")

        assert_workspace(repo_path, base_files)
        assert_noent(repo_path, "new")
        assert_status(legit_cmd, "")

    def test_it_removes_a_file_from_a_non_empty_directory(
        self,
        write_file: WriteFile,
        commit_and_checkout: CommitAndCheckout,
        repo_path: Path,
        base_files: dict[str, str],
        legit_cmd: LegitCmd,
    ) -> None:
        write_file("outer/94.txt", "94")
        commit_and_checkout("@^")
        assert_workspace(repo_path, base_files)
        assert_status(legit_cmd, "")

    def test_it_fails_to_remove_a_modified_file(
        self, write_file: WriteFile, commit_all: CommitAll, legit_cmd: LegitCmd
    ) -> None:
        write_file("outer/94.txt", "94")
        commit_all()

        write_file("outer/94.txt", "conflict")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_stale_file(stderr, "outer/94.txt")

    def test_it_fails_to_remove_a_changed_mode_file(
        self,
        write_file: WriteFile,
        make_executable: MakeExecutable,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
    ) -> None:
        write_file("outer/94.txt", "94")
        commit_all()

        make_executable("outer/94.txt")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_stale_file(stderr, "outer/94.txt")

    def test_it_leaves_a_deleted_file_deleted(
        self,
        write_file: WriteFile,
        delete: Delete,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
        repo_path: Path,
        base_files: dict[str, str],
    ) -> None:
        write_file("outer/94.txt", "94")
        commit_all()

        delete("outer/94.txt")
        legit_cmd("checkout", "@^")

        assert_workspace(repo_path, base_files)
        assert_status(legit_cmd, "")

    def test_it_leaves_a_deleted_directory_deleted(
        self,
        write_file: WriteFile,
        delete: Delete,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
        repo_path: Path,
    ) -> None:
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

    def test_it_fails_to_remove_a_staged_file(
        self, write_file: WriteFile, commit_all: CommitAll, legit_cmd: LegitCmd
    ) -> None:
        write_file("outer/94.txt", "94")
        commit_all()

        write_file("outer/94.txt", "conflict")
        legit_cmd("add", ".")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_stale_file(stderr, "outer/94.txt")

    def test_it_fails_to_remove_a_staged_changed_mode_file(
        self,
        write_file: WriteFile,
        make_executable: MakeExecutable,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
    ) -> None:
        write_file("outer/94.txt", "94")
        commit_all()

        make_executable("outer/94.txt")
        legit_cmd("add", ".")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_stale_file(stderr, "outer/94.txt")

    def test_it_leaves_an_unindexed_file_deleted(
        self,
        write_file: WriteFile,
        delete: Delete,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
        repo_path: Path,
        base_files: dict[str, str],
    ) -> None:
        write_file("outer/94.txt", "94")
        commit_all()

        delete("outer/94.txt")
        delete(".git/index")
        legit_cmd("add", ".")
        legit_cmd("checkout", "@^")

        assert_workspace(repo_path, base_files)
        assert_status(legit_cmd, "")

    def test_fails_to_remove_an_unindexed_and_untracked_file(
        self,
        write_file: WriteFile,
        delete: Delete,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
    ) -> None:
        write_file("outer/94.txt", "94")
        commit_all()

        delete("outer/94.txt")
        delete(".git/index")
        legit_cmd("add", ".")

        write_file("outer/94.txt", "conflict")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_remove_conflict(stderr, "outer/94.txt")

    def test_it_leaves_an_unindexed_directory_deleted(
        self,
        write_file: WriteFile,
        delete: Delete,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
        repo_path: Path,
    ) -> None:
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

    def test_it_fails_to_remove_with_a_file_at_a_parent_path(
        self,
        write_file: WriteFile,
        delete: Delete,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
    ) -> None:
        write_file("outer/inner/94.txt", "94")
        commit_all()

        delete("outer/inner")
        write_file("outer/inner", "conflict")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_stale_file(stderr, "outer/inner/94.txt")

    def test_it_removes_a_file_with_a_staged_file_at_a_parent_path(
        self,
        write_file: WriteFile,
        delete: Delete,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
        repo_path: Path,
    ) -> None:
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

    def test_it_fails_to_remove_with_an_unstaged_file_at_a_parent_path(
        self,
        write_file: WriteFile,
        delete: Delete,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
    ) -> None:
        write_file("outer/inner/94.txt", "94")
        commit_all()

        delete("outer/inner")
        delete(".git/index")
        legit_cmd("add", ".")
        write_file("outer/inner", "conflict")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_remove_conflict(stderr, "outer/inner")

    def test_it_fails_to_remove_with_a_file_at_a_child_path(
        self,
        write_file: WriteFile,
        delete: Delete,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
    ) -> None:
        write_file("outer/94.txt", "94")
        commit_all()

        delete("outer/94.txt")
        write_file("outer/94.txt/extra.log", "conflict")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_stale_file(stderr, "outer/94.txt")

    def test_it_removes_a_file_with_a_staged_file_at_a_child_path(
        self,
        write_file: WriteFile,
        delete: Delete,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
        repo_path: Path,
        base_files: dict[str, str],
    ) -> None:
        write_file("outer/94.txt", "94")
        commit_all()

        delete("outer/94.txt")
        write_file("outer/94.txt/extra.log", "conflict")
        legit_cmd("add", ".")
        legit_cmd("checkout", "@^")

        assert_workspace(repo_path, base_files)
        assert_status(legit_cmd, "")

    def test_it_adds_a_file(
        self,
        delete: Delete,
        commit_and_checkout: CommitAndCheckout,
        repo_path: Path,
        base_files: dict[str, str],
        legit_cmd: LegitCmd,
    ) -> None:
        delete("1.txt")
        commit_and_checkout("@^")

        assert_workspace(repo_path, base_files)
        assert_status(legit_cmd, "")

    def test_it_adds_a_file_to_a_directory(
        self,
        delete: Delete,
        commit_and_checkout: CommitAndCheckout,
        repo_path: Path,
        base_files: dict[str, str],
        legit_cmd: LegitCmd,
    ) -> None:
        delete("outer/2.txt")
        commit_and_checkout("@^")

        assert_workspace(repo_path, base_files)
        assert_status(legit_cmd, "")

    def test_it_adds_a_directory(
        self,
        delete: Delete,
        commit_and_checkout: CommitAndCheckout,
        repo_path: Path,
        base_files: dict[str, str],
        legit_cmd: LegitCmd,
    ) -> None:
        delete("outer")
        commit_and_checkout("@^")

        assert_workspace(repo_path, base_files)
        assert_status(legit_cmd, "")

    def test_it_fails_to_add_an_untracked_file(
        self,
        delete: Delete,
        write_file: WriteFile,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
    ) -> None:
        delete("outer/2.txt")
        commit_all()

        write_file("outer/2.txt", "conflict")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_overwrite_conflict(stderr, "outer/2.txt")

    def test_it_fails_to_add_an_added_file(
        self,
        delete: Delete,
        write_file: WriteFile,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
    ) -> None:
        delete("outer/2.txt")
        commit_all()

        write_file("outer/2.txt", "conflict")
        legit_cmd("add", ".")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_stale_file(stderr, "outer/2.txt")

    def test_it_adds_a_staged_equal_file(
        self,
        delete: Delete,
        write_file: WriteFile,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
        repo_path: Path,
        base_files: dict[str, str],
    ) -> None:
        delete("outer/2.txt")
        commit_all()

        write_file("outer/2.txt", "2")
        legit_cmd("add", ".")
        legit_cmd("checkout", "@^")

        assert_workspace(repo_path, base_files)
        assert_status(legit_cmd, "")

    def test_it_fails_to_add_with_an_untracked_file_at_a_parent_path(
        self,
        delete: Delete,
        write_file: WriteFile,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
    ) -> None:
        delete("outer/inner/3.txt")
        commit_all()

        delete("outer/inner")
        write_file("outer/inner", "conflict")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_overwrite_conflict(stderr, "outer/inner")

    def test_it_adds_a_file_with_an_added_file_at_a_parent_path(
        self,
        delete: Delete,
        write_file: WriteFile,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
        repo_path: Path,
        base_files: dict[str, str],
    ) -> None:
        delete("outer/inner/3.txt")
        commit_all()

        delete("outer/inner")
        write_file("outer/inner", "conflict")
        legit_cmd("add", ".")
        legit_cmd("checkout", "@^")

        assert_workspace(repo_path, base_files)
        assert_status(legit_cmd, "")

    def test_it_fails_to_add_with_an_untracked_file_at_a_child_path(
        self,
        delete: Delete,
        write_file: WriteFile,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
    ) -> None:
        delete("outer/2.txt")
        commit_all()

        write_file("outer/2.txt/extra.log", "conflict")

        *_, stderr = legit_cmd("checkout", "@^")
        assert_stale_directory(stderr, "outer/2.txt")

    def test_it_adds_a_file_with_an_added_file_at_a_child_path(
        self,
        delete: Delete,
        write_file: WriteFile,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
        repo_path: Path,
        base_files: dict[str, str],
    ) -> None:
        delete("outer/2.txt")
        commit_all()

        write_file("outer/2.txt/extra.log", "conflict")
        legit_cmd("add", ".")
        legit_cmd("checkout", "@^")

        assert_workspace(repo_path, base_files)
        assert_status(legit_cmd, "")

    def test_it_replaces_a_file_with_a_directory(
        self,
        delete: Delete,
        write_file: WriteFile,
        commit_and_checkout: CommitAndCheckout,
        repo_path: Path,
        base_files: dict[str, str],
        legit_cmd: LegitCmd,
    ) -> None:
        delete("outer/inner")
        write_file("outer/inner", "in")
        commit_and_checkout("@^")

        assert_workspace(repo_path, base_files)
        assert_status(legit_cmd, "")

    def test_it_replaces_a_directory_with_a_file(
        self,
        delete: Delete,
        write_file: WriteFile,
        commit_and_checkout: CommitAndCheckout,
        repo_path: Path,
        base_files: dict[str, str],
        legit_cmd: LegitCmd,
    ) -> None:
        delete("outer/2.txt")
        write_file("outer/2.txt/nested.log", "nested")
        commit_and_checkout("@^")

        assert_workspace(repo_path, base_files)
        assert_status(legit_cmd, "")

    def test_it_maintains_workspace_modifications(
        self,
        write_file: WriteFile,
        delete: Delete,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
        repo_path: Path,
    ) -> None:
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

    def test_it_maintains_index_modifications(
        self,
        write_file: WriteFile,
        commit_all: CommitAll,
        legit_cmd: LegitCmd,
        repo_path: Path,
        base_files: dict[str, str],
    ) -> None:
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


class TestWithAChainOfCommits:
    @pytest.fixture(autouse=True)
    def setup(self, write_file: WriteFile, commit: Commit, legit_cmd: LegitCmd) -> None:
        for msg in ["first", "second", "third"]:
            write_file("file.txt", msg)
            legit_cmd("add", ".")
            commit(msg)

        _ = legit_cmd("branch", "topic")
        _ = legit_cmd("branch", "second", "@^")

    def test_it_links_HEAD_to_branch(
        self, legit_cmd: LegitCmd, repo: Repository
    ) -> None:
        _ = legit_cmd("checkout", "topic")
        assert repo.refs.current_ref().path == "refs/heads/topic"

    def test_it_resolves_HEAD_to_same_object_as_branch(
        self, legit_cmd: LegitCmd, repo: Repository
    ) -> None:
        _ = legit_cmd("checkout", "topic")
        assert repo.refs.read_ref("topic") == repo.refs.read_head()

    def test_it_prints_message_when_switching_to_same_branch(
        self, legit_cmd: LegitCmd
    ) -> None:
        _ = legit_cmd("checkout", "topic")
        *_, stderr = legit_cmd("checkout", "topic")
        assert_stderr(stderr, "Already on 'topic'\n")

    def test_it_prints_a_message_when_switching_to_another_branch(
        self, legit_cmd: LegitCmd
    ) -> None:
        _ = legit_cmd("checkout", "topic")
        *_, stderr = legit_cmd("checkout", "second")
        assert_stderr(stderr, "Switched to branch 'second'\n")

    def test_it_prints_warning_when_detaching_HEAD(
        self, legit_cmd: LegitCmd, repo: Repository
    ) -> None:
        _ = legit_cmd("checkout", "topic")
        *_, stderr = legit_cmd("checkout", "@")
        short = repo.database.short_oid(cast(str, repo.refs.read_head()))
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
        assert_stderr(stderr, expected)

    def test_it_detaches_HEAD_on_relative_revision(
        self, legit_cmd: LegitCmd, repo: Repository
    ) -> None:
        _ = legit_cmd("checkout", "topic^")
        assert repo.refs.current_ref().path == "HEAD"

    def test_puts_revision_value_in_HEAD(
        self, legit_cmd: LegitCmd, repo: Repository, resolve_revision: ResolveRevision
    ) -> None:
        _ = legit_cmd("checkout", "topic^")
        assert repo.refs.read_head() == resolve_revision("topic^")

    def test_it_prints_message_when_switching_to_same_commit(
        self, legit_cmd: LegitCmd, repo: Repository, resolve_revision: ResolveRevision
    ) -> None:
        _ = legit_cmd("checkout", "topic^")
        short = repo.database.short_oid(resolve_revision("@"))
        *_, stderr = legit_cmd("checkout", "@")
        assert_stderr(stderr, f"HEAD is now at {short} second\n")

    def test_it_prints_a_message_when_switching_to_a_different_commit(
        self, legit_cmd: LegitCmd, repo: Repository, resolve_revision: ResolveRevision
    ) -> None:
        _ = legit_cmd("checkout", "topic^")
        a = repo.database.short_oid(resolve_revision("@"))
        b = repo.database.short_oid(resolve_revision("@^"))
        *_, stderr = legit_cmd("checkout", "topic^^")
        assert_stderr(
            stderr,
            textwrap.dedent(f"""\
            Previous HEAD position was {a} second
            HEAD is now at {b} first
            """),
        )

    def test_it_prints_a_message_when_switching_to_a_branch_with_same_ID(
        self, legit_cmd: LegitCmd
    ) -> None:
        _ = legit_cmd("checkout", "topic^")
        *_, stderr = legit_cmd("checkout", "second")
        assert_stderr(stderr, "Switched to branch 'second'\n")

    def test_it_prints_a_message_when_switching_to_a_branch_from_detached(
        self, legit_cmd: LegitCmd, repo: Repository, resolve_revision: ResolveRevision
    ) -> None:
        _ = legit_cmd("checkout", "topic^")
        short = repo.database.short_oid(resolve_revision("@"))
        *_, stderr = legit_cmd("checkout", "topic")
        assert_stderr(
            stderr,
            textwrap.dedent(f"""\
            Previous HEAD position was {short} second
            Switched to branch 'topic'
            """),
        )
