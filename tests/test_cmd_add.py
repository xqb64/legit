from legit.repository import Repository
from tests.cmd_helpers import assert_stderr, assert_stdout
from tests.conftest import (
    LegitCmd,
    MakeExecutable,
    MakeUnreadable,
    WriteFile,
)


def get_index(repo: Repository) -> list[tuple[int, str]]:
    repo.index.load()
    return sorted(
        [(entry.mode(), str(entry.path)) for entry in repo.index.entries.values()]
    )


def test_it_adds_regular_file_to_the_index(
    write_file: WriteFile, legit_cmd: LegitCmd, repo: Repository
) -> None:
    write_file("hello.txt", "hello")
    cmd, *_ = legit_cmd("add", "hello.txt")
    assert cmd.status == 0
    assert get_index(repo) == [(0o100644, "hello.txt")]


def test_it_adds_executable_file_to_the_index(
    write_file: WriteFile,
    make_executable: MakeExecutable,
    legit_cmd: LegitCmd,
    repo: Repository,
) -> None:
    write_file("hello.txt", "hello")
    make_executable("hello.txt")
    cmd, *_ = legit_cmd("add", "hello.txt")
    assert cmd.status == 0
    assert get_index(repo) == [(0o100755, "hello.txt")]


def test_it_adds_multiple_files_to_the_index(
    write_file: WriteFile, legit_cmd: LegitCmd, repo: Repository
) -> None:
    write_file("hello.txt", "hello")
    write_file("world.txt", "world")
    cmd, *_ = legit_cmd("add", "hello.txt", "world.txt")
    assert cmd.status == 0
    assert get_index(repo) == [
        (0o100644, "hello.txt"),
        (0o100644, "world.txt"),
    ]


def test_it_incrementally_adds_files_to_the_index(
    write_file: WriteFile, legit_cmd: LegitCmd, repo: Repository
) -> None:
    write_file("hello.txt", "hello")
    write_file("world.txt", "world")

    _ = legit_cmd("add", "world.txt")
    assert get_index(repo) == [(0o100644, "world.txt")]

    _ = legit_cmd("add", "hello.txt")
    assert get_index(repo) == [
        (0o100644, "hello.txt"),
        (0o100644, "world.txt"),
    ]


def test_it_adds_a_directory_to_the_index(
    write_file: WriteFile, legit_cmd: LegitCmd, repo: Repository
) -> None:
    write_file("a-dir/nested.txt", "content")
    _ = legit_cmd("add", "a-dir")
    assert get_index(repo) == [(0o100644, "a-dir/nested.txt")]


def test_it_adds_the_repository_root_to_the_index(
    write_file: WriteFile, legit_cmd: LegitCmd, repo: Repository
) -> None:
    write_file("a/b/c/file.txt", "content")
    _ = legit_cmd("add", ".")
    assert get_index(repo) == [(0o100644, "a/b/c/file.txt")]


def test_it_is_silent_on_success(write_file: WriteFile, legit_cmd: LegitCmd) -> None:
    write_file("hello.txt", "hello")
    cmd, _, stdout, stderr = legit_cmd("add", "hello.txt")
    assert cmd.status == 0
    assert_stdout(stdout, "")
    assert_stderr(stderr, "")


def test_it_fails_for_nonexistent_files(legit_cmd: LegitCmd, repo: Repository) -> None:
    cmd, *_, stderr = legit_cmd("add", "no-such-file")
    assert_stderr(stderr, "fatal: pathspec 'no-such-file' did not match any files\n")
    assert cmd.status == 128
    assert get_index(repo) == []


def test_it_fails_for_unreadable_files(
    write_file: WriteFile,
    make_unreadable: MakeUnreadable,
    legit_cmd: LegitCmd,
    repo: Repository,
) -> None:
    write_file("secret.txt", "")
    make_unreadable("secret.txt")
    cmd, *_, stderr = legit_cmd("add", "secret.txt")
    assert cmd.status == 128
    expected = (
        "error: open('secret.txt'): Permission denied\nfatal: adding files failed\n"
    )
    assert_stderr(stderr, expected)
    assert get_index(repo) == []


def test_it_fails_if_the_index_is_locked(
    write_file: WriteFile, legit_cmd: LegitCmd, repo: Repository
) -> None:
    write_file("file.txt", "")
    write_file(".git/index.lock", "")
    cmd, *_ = legit_cmd("add", "file.txt")
    assert cmd.status == 128
    assert get_index(repo) == []
