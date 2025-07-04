from legit.common_ancestors import CommonAncestors


class FastForwardMixin:
    def fast_forward_error(self, old_oid, new_oid):
        if not (old_oid and new_oid):
            return None

        if not self.repo.database.has(old_oid):
            return "fetch first"

        if not self.is_fast_forward(old_oid, new_oid):
            return "non-fast-forward"

    def is_fast_forward(self, old_oid, new_oid):
        common = CommonAncestors(self.repo.database, old_oid, [new_oid])
        common.find()
        return common.is_marked(old_oid, "parent2")
