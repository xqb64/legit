import pytest
from io import StringIO

from legit.command import Command
from legit.repository import Repository

def get_index(repo):
    """
    Load the index and return a list of (mode, path) tuples.
    """
    repo.index.load()
    return [(entry.mode(), str(entry.path)) for entry in repo.index.entries.values()]


def test_add_regular_file(write_file, legit_cmd, repo):
    write_file("hello.txt", "hello")
    cmd, stdin, stdout, stderr = legit_cmd("add", "hello.txt")
    assert cmd.status == 0
    assert get_index(repo) == [(0o100644, "hello.txt")]


def test_add_executable_file(write_file, make_executable, legit_cmd, repo):
    write_file("hello.txt", "hello")
    make_executable("hello.txt")
    cmd, stdin, stdout, stderr = legit_cmd("add", "hello.txt")
    assert cmd.status == 0
    assert get_index(repo) == [(0o100755, "hello.txt")]


def test_add_multiple_files(write_file, legit_cmd, repo):
    write_file("hello.txt", "hello")
    write_file("world.txt", "world")
    cmd, stdin, stdout, stderr = legit_cmd("add", "hello.txt", "world.txt")
    assert cmd.status == 0
    assert sorted(get_index(repo)) == sorted([
        (0o100644, "hello.txt"),
        (0o100644, "world.txt"),
    ])


def test_incremental_add(write_file, legit_cmd, repo):
    write_file("hello.txt", "hello")
    write_file("world.txt", "world")
    # First add world
    cmd1, *_ = legit_cmd("add", "world.txt")
    assert cmd1.status == 0
    assert get_index(repo) == [(0o100644, "world.txt")]
    # Then add hello
    cmd2, *_ = legit_cmd("add", "hello.txt")
    assert cmd2.status == 0
    assert sorted(get_index(repo)) == sorted([
        (0o100644, "hello.txt"),
        (0o100644, "world.txt"),
    ])


def test_add_directory(write_file, legit_cmd, repo):
    write_file("a-dir/nested.txt", "content")
    cmd, *_ = legit_cmd("add", "a-dir")
    assert cmd.status == 0
    assert get_index(repo) == [(0o100644, "a-dir/nested.txt")]


def test_add_root(write_file, legit_cmd, repo):
    write_file("a/b/c/file.txt", "content")
    cmd, *_ = legit_cmd("add", ".")
    assert cmd.status == 0
    assert get_index(repo) == [(0o100644, "a/b/c/file.txt")]


def test_silent_on_success(write_file, legit_cmd, repo):
    write_file("hello.txt", "hello")
    cmd, stdin, stdout, stderr = legit_cmd("add", "hello.txt")
    assert cmd.status == 0
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == ""


def test_nonexistent_file(legit_cmd, repo):
    cmd, stdin, stdout, stderr = legit_cmd("add", "no-such-file")
    assert cmd.status == 128
    assert stderr.getvalue() == "fatal: pathspec \"no-such-file\" did not match any files\n"
    assert get_index(repo) == []


def test_unreadable_file(write_file, make_unreadable, legit_cmd, repo):
    write_file("secret.txt", "")
    make_unreadable("secret.txt")
    cmd, stdin, stdout, stderr = legit_cmd("add", "secret.txt")
    assert cmd.status == 128
    expected = (
        "error: open(\"secret.txt\"): Permission denied\n"
        "fatal: adding files failed\n"
    )
    assert stderr.getvalue() == expected
    assert get_index(repo) == []


def test_index_locked(write_file, legit_cmd, repo):
    write_file("file.txt", "")
    write_file(".git/index.lock", "")
    cmd, stdin, stdout, stderr = legit_cmd("add", "file.txt")
    assert cmd.status == 128
    assert get_index(repo) == []

