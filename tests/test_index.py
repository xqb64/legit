import os
import secrets
from pathlib import Path

import pytest

from legit.index import Index


@pytest.fixture
def index_path(tmp_path: Path) -> Path:
    return tmp_path / "index"


@pytest.fixture
def index(index_path: Path) -> Index:
    return Index(index_path)


@pytest.fixture
def stat() -> os.stat_result:
    return os.stat(__file__)


@pytest.fixture
def oid() -> str:
    return secrets.token_hex(20)


def test_it_adds_single_file(index: Index, oid: str, stat: os.stat_result) -> None:
    index.add(Path("alice.txt"), oid, stat)

    assert [str(entry.path) for entry in index.entries.values()] == ["alice.txt"]


def test_it_replaces_a_file_with_directory(
    index: Index, oid: str, stat: os.stat_result
) -> None:
    index.add(Path("alice.txt"), oid, stat)
    index.add(Path("bob.txt"), oid, stat)

    index.add(Path("alice.txt/nested.txt"), oid, stat)

    assert [
        str(entry.path)
        for entry in sorted(index.entries.values(), key=lambda x: x.path)
    ] == ["alice.txt/nested.txt", "bob.txt"]


def test_it_replaces_a_directory_with_a_file(
    index: Index, oid: str, stat: os.stat_result
) -> None:
    index.add(Path("alice.txt"), oid, stat)
    index.add(Path("nested/bob.txt"), oid, stat)

    index.add(Path("nested"), oid, stat)

    assert [
        str(entry.path)
        for entry in sorted(index.entries.values(), key=lambda x: x.path)
    ] == ["alice.txt", "nested"]


def test_it_recursively_replaces_directory_with_a_file(
    index: Index, oid: str, stat: os.stat_result
) -> None:
    index.add(Path("alice.txt"), oid, stat)
    index.add(Path("nested/bob.txt"), oid, stat)
    index.add(Path("nested/inner/claire.txt"), oid, stat)

    index.add(Path("nested"), oid, stat)

    assert [
        str(entry.path)
        for entry in sorted(index.entries.values(), key=lambda x: x.path)
    ] == ["alice.txt", "nested"]
