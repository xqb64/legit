from __future__ import annotations

from legit.common_ancestors import CommonAncestors
from legit.database import Database


class Bases:
    def __init__(self, database: Database, one: str, two: str) -> None:
        self.database = database
        self.common = CommonAncestors(self.database, one, [two])

    def find(self) -> list[str]:
        self.commits = self.common.find()
        if len(self.commits) <= 1:
            return self.commits

        self.redundant: set[str] = set()

        for commit in self.commits:
            self.filter_commit(commit)

        return [c for c in self.commits if c not in self.redundant]

    def filter_commit(self, commit: str) -> None:
        if commit in self.redundant:
            return

        others = [
            oid for oid in self.commits if oid != commit and oid not in self.redundant
        ]

        common = CommonAncestors(self.database, commit, others)

        common.find()

        if common.is_marked(commit, "parent2"):
            self.redundant.add(commit)

        others[:] = [oid for oid in others if common.is_marked(oid, "parent1")]

        self.redundant.update(others)
