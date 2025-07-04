from collections import defaultdict
from legit.commit import Commit
from legit.database import Database


class CommonAncestors:
    def __init__(self, database: Database, one: str, twos: str) -> None:
        self.database: Database = database
        self.flags = defaultdict(set)
        self.queue = []

        self.results = []

        self.insert_by_date(self.queue, self.database.load(one))
        self.flags[one].add("parent1")

        for two in twos:
            self.insert_by_date(self.queue, self.database.load(two))
            self.flags[two].add("parent2")

    def insert_by_date(self, structure, commit) -> None:
        index = next(
            (i for i, c in enumerate(structure) if c.date() < commit.date()),
            None,
        )
        pos = index if index is not None else len(structure)
        structure.insert(pos, commit)

    def find(self) -> list[str]:
        while not self._all_stale():
            self._process_queue()

        return [
            commit.oid
            for commit in self.results
            if not self.is_marked(commit.oid, "stale")
        ]

    def _all_stale(self) -> bool:
        return all(self.is_marked(c.oid, "stale") for c in self.queue)

    def is_marked(self, oid: str, flag: str) -> bool:
        return flag in self.flags[oid]

    def _process_queue(self) -> None:
        commit = self.queue.pop(0)

        flags = self.flags[commit.oid]

        if flags == set(["parent1", "parent2"]):
            flags.add("result")

            self.insert_by_date(self.results, commit)
            self.add_parents(commit, flags | {"stale"})
        else:
            self.add_parents(commit, flags)

    def add_parents(self, commit: Commit, flags: set[str]) -> None:
        for parent_oid in commit.parents:
            if self.flags[parent_oid].issuperset(flags):
                continue

            self.flags[parent_oid].update(flags)

            parent_commit = self.database.load(parent_oid)
            self.insert_by_date(self.queue, parent_commit)
