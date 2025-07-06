import os
import secrets
import pytest

from legit.index import Index

@pytest.fixture
def index_path(tmp_path):
    return tmp_path / "index"


@pytest.fixture
def index(index_path):
    return Index(index_path)


@pytest.fixture
def stat():
    return os.stat(__file__)


@pytest.fixture
def oid():
    return secrets.token_hex(20)


def test_it_adds_single_file(index, oid, stat):
    index.add("alice.txt", oid, stat)

    assert [str(entry.path) for entry in index.entries.values()] == ["alice.txt"]


def test_it_replaces_a_file_with_directory(index, oid, stat):
    index.add("alice.txt", oid, stat)
    index.add("bob.txt", oid, stat)

    index.add("alice.txt/nested.txt", oid, stat)

    assert [str(entry.path) for entry in sorted(index.entries.values(), key=lambda x: x.path)] == ["alice.txt/nested.txt", "bob.txt"]


def test_it_replaces_a_directory_with_a_file(index, oid, stat):
    index.add("alice.txt", oid, stat)
    index.add("nested/bob.txt", oid, stat)

    index.add("nested", oid, stat)
    
    assert [str(entry.path) for entry in sorted(index.entries.values(), key=lambda x: x.path)] == ["alice.txt", "nested"]


def test_it_recursively_replaces_directory_with_a_file(index, oid, stat):
    index.add("alice.txt", oid, stat)
    index.add("nested/bob.txt", oid, stat)
    index.add("nested/inner/claire.txt", oid, stat)

    index.add("nested", oid, stat)

    assert [str(entry.path) for entry in sorted(index.entries.values(), key=lambda x: x.path)] == ["alice.txt", "nested"]
