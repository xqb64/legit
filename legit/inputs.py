from __future__ import annotations

from dataclasses import dataclass

from legit.bases import Bases
from legit.repository import Repository
from legit.revision import Revision


class Inputs:
    def __init__(self, repo: Repository, left_name: str, right_name: str) -> None:
        self.repo = repo
        self.left_name = left_name
        self.right_name = right_name

        self.left_oid = self.resolve_rev(self.left_name)
        self.right_oid = self.resolve_rev(self.right_name)

        common = Bases(self.repo.database, self.left_oid, self.right_oid)
        self.base_oids = common.find()

    def resolve_rev(self, rev: str) -> str:
        return Revision(self.repo, rev).resolve(Revision.COMMIT)

    def are_already_merged(self) -> bool:
        return self.base_oids == [self.right_oid]

    def are_fast_forward(self) -> bool:
        return self.base_oids == [self.left_oid]


@dataclass
class CherryPick:
    left_name: str
    right_name: str
    left_oid: str
    right_oid: str
    base_oids: list[str]
