from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from legit.common_ancestors import CommonAncestors

if TYPE_CHECKING:
    from legit.repository import Repository


class FastForwardMixin:
    repo: Repository

    def fast_forward_error(
        self, old_oid: Optional[str], new_oid: Optional[str]
    ) -> Optional[str]:
        if not (old_oid and new_oid):
            return None

        if not self.repo.database.has(old_oid):
            return "fetch first"

        if not self.is_fast_forward(old_oid, new_oid):
            return "non-fast-forward"

        return None

    def is_fast_forward(self, old_oid: str, new_oid: str) -> bool:
        common = CommonAncestors(self.repo.database, old_oid, [new_oid])
        common.find()
        return common.is_marked(old_oid, "parent2")
