from __future__ import annotations

from pathlib import Path
from legit.repository import Repository
from legit.blob import Blob
from legit.commit import Commit
from legit.tree import Tree
from legit.db_entry import DatabaseEntry

repo = Repository(Path.cwd() / ".git")

head_oid = repo.refs.read_head()
commit = repo.database.load(head_oid)


def show_tree(repo: Repository, oid: str, prefix: str = "") -> None:
    tree: Blob | Commit | Tree = repo.database.load(oid)

    assert isinstance(tree, Tree)

    for name, entry in tree.entries.items():
        path = Path(prefix) / name
        assert isinstance(entry, DatabaseEntry)
        if entry.is_tree():
            show_tree(repo, entry.oid, str(path))
        else:
            mode = oct(entry.mode)[2:]
            print(f"{mode} {entry.oid} {path}")


assert isinstance(commit, Commit)
show_tree(repo, commit.tree)
