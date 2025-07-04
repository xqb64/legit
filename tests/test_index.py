import os
import secrets
from pathlib import Path
import pytest

from legit.index import Index

@pytest.fixture

def index_path(tmp_path):
    # Create a path for the index within a temporary directory
    return tmp_path / "index"

@pytest.fixture
def index(index_path):
    # Initialize the Index with the given path
    return Index(index_path)

@pytest.fixture
def stat():
    # Use the current test file's metadata for the stat object
    return os.stat(__file__)

@pytest.fixture
def oid():
    # Generate a random object ID (40 hex characters)
    return secrets.token_hex(20)


def test_adds_single_file(index, oid, stat):
    # Add a single file to the index
    index.add("alice.txt", oid, stat)

    # Verify that the entry was added with the correct path
    assert [str(entry.path) for entry in index.entries.values()] == ["alice.txt"]


def test_replaces_a_file_with_directory(index, oid, stat):
    index.add("alice.txt", oid, stat)
    index.add("bob.txt", oid, stat)

    index.add("alice.txt/nested.txt", oid, stat)

    assert [str(entry.path) for entry in sorted(index.entries.values(), key=lambda x: x.path)] == ["alice.txt/nested.txt", "bob.txt"]


def test_replaces_a_directory_with_a_file(index, oid, stat):
    index.add("alice.txt", oid, stat)
    index.add("nested/bob.txt", oid, stat)

    index.add("nested", oid, stat)
    
    assert [str(entry.path) for entry in sorted(index.entries.values(), key=lambda x: x.path)] == ["alice.txt", "nested"]


def test_recursively_replaces_directory_with_a_file(index, oid, stat):
    index.add("alice.txt", oid, stat)
    index.add("nested/bob.txt", oid, stat)
    index.add("nested/inner/claire.txt", oid, stat)

    index.add("nested", oid, stat)

    assert [str(entry.path) for entry in sorted(index.entries.values(), key=lambda x: x.path)] == ["alice.txt", "nested"]
