from pathlib import Path
from typing import Dict, Any

import pytest

from legit.database import Database, DatabaseEntry
from legit.blob import Blob
from legit.tree import Tree


class FakeEntry:
    def __init__(self, path: str, oid: str, mode: int):
        self.path = path
        self.oid = oid
        self.mode_bits = mode

    def parent_directories(self) -> list[Path]:
        return list(Path(self.path).parents)[:-1][::-1]

    def basename(self) -> str:
        return Path(self.path).name
    
    def mode(self) -> int:
        return self.mode_bits


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    test_objects_path = tmp_path / "test-objects"
    test_objects_path.mkdir()
    return test_objects_path


def store_tree(database: Database, contents: Dict[str, Any]) -> str:
    entries = {}
    for path, data in contents.items():
        blob = Blob(data.encode())
        database.store(blob)
        entry = FakeEntry(path, blob.oid, 0o100644)
        entries[Path(path)] = entry

    tree = Tree.from_entries(entries)

    def store_all(t: Tree):
        database.store(t)

    tree.traverse(store_all)
    return tree.oid


def tree_diff(database: Database, a: str, b: str):
    return database.tree_diff(a, b)


def test_it_reports_a_changed_file(db_path: Path):
    db = Database(db_path)
    tree_a = store_tree(db, {
        "alice.txt": "alice",
        "bob.txt": "bob"
    })
    tree_b = store_tree(db, {
        "alice.txt": "changed",
        "bob.txt": "bob"
    })

    diff = tree_diff(db, tree_a, tree_b)

    oid_alice_a = "ca56b59dbf8c0884b1b9ceb306873b24b73de969"
    oid_alice_b = "21fb1eca31e64cd3914025058b21992ab76edcf9"
    
    expected = {
        Path("alice.txt"): [
            DatabaseEntry(oid_alice_a, 0o100644),
            DatabaseEntry(oid_alice_b, 0o100644)
        ]
    }
    assert diff == expected


def test_it_reports_an_added_file(db_path: Path):
    db = Database(db_path)
    tree_a = store_tree(db, {
        "alice.txt": "alice"
    })
    tree_b = store_tree(db, {
        "alice.txt": "alice",
        "bob.txt": "bob"
    })
    
    diff = tree_diff(db, tree_a, tree_b)

    oid_bob = "2529de8969e5ee206e572ed72a0389c3115ad95c"
    
    expected = {
        Path("bob.txt"): [
            None,
            DatabaseEntry(oid_bob, 0o100644)
        ]
    }
    assert diff == expected


def test_it_reports_a_deleted_file(db_path: Path):
    db = Database(db_path)
    tree_a = store_tree(db, {
        "alice.txt": "alice",
        "bob.txt": "bob"
    })
    tree_b = store_tree(db, {
        "alice.txt": "alice"
    })

    diff = tree_diff(db, tree_a, tree_b)

    oid_bob = "2529de8969e5ee206e572ed72a0389c3115ad95c"

    expected = {
        Path("bob.txt"): [
            DatabaseEntry(oid_bob, 0o100644),
            None
        ]
    }
    assert diff == expected


def test_it_reports_an_added_file_inside_a_directory(db_path: Path):
    db = Database(db_path)
    tree_a = store_tree(db, {
        "1.txt": "1",
        "outer/2.txt": "2"
    })
    tree_b = store_tree(db, {
        "1.txt": "1",
        "outer/2.txt": "2",
        "outer/new/4.txt": "4"
    })

    diff = tree_diff(db, tree_a, tree_b)
    
    oid_4 = "bf0d87ab1b2b0ec1a11a3973d2845b42413d9767"

    expected = {
        Path("outer/new/4.txt"): [
            None,
            DatabaseEntry(oid_4, 0o100644)
        ]
    }
    assert diff == expected


def test_it_reports_a_deleted_file_inside_a_directory(db_path: Path):
    db = Database(db_path)
    tree_a = store_tree(db, {
        "1.txt": "1",
        "outer/2.txt": "2",
        "outer/inner/3.txt": "3"
    })
    tree_b = store_tree(db, {
        "1.txt": "1",
        "outer/2.txt": "2"
    })
    
    diff = tree_diff(db, tree_a, tree_b)
    
    oid_3 = "e440e5c842586965a7fb77deda2eca68612b1f53"

    expected = {
        Path("outer/inner/3.txt"): [
            DatabaseEntry(oid_3, 0o100644),
            None
        ]
    }
    assert diff == expected
