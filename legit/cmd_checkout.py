from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Optional, cast

from legit.cmd_base import Base
from legit.commit import Commit
from legit.db_entry import DatabaseEntry
from legit.migration import Migration
from legit.refs import Refs
from legit.revision import Revision

DETACHED_HEAD_MESSAGE = textwrap.dedent("""\
    You are in 'detached HEAD' state. You can look around, make experimental
    changes and commit them, and you can discard any commits you make in this
    state without impacting any branches by performing another checkout.

    If you want to create a new branch to retain commits you create, you may
    do so (now or later) by using the branch command. Example:

        legit branch <new-branch-name>
""")


class Checkout(Base):
    def run(self) -> None:
        self.target: str = self.args[0]

        self.current_ref: Refs.SymRef = self.repo.refs.current_ref()
        self.current_oid: Optional[str] = self.current_ref.read_oid()

        revision: Revision = Revision(self.repo, self.target)

        self.target_oid: str | None = None

        try:
            self.target_oid = revision.resolve(Revision.COMMIT)
        except Revision.InvalidObject as e:
            self.handle_invalid_object(revision, e)

        self.repo.index.load_for_update()

        tree_diff = self.repo.database.tree_diff(
            cast(str, self.current_oid), cast(str, self.target_oid)
        )
        migration = self.repo.migration(tree_diff)

        try:
            migration.apply_changes()
        except Migration.Conflict:
            self.handle_migration_conflict(migration)

        self.repo.index.write_updates()
        self.repo.refs.set_head(self.target, cast(str, self.target_oid))

        self.new_ref = self.repo.refs.current_ref()

        self.print_previous_head()
        self.print_detachment_notice()
        self.print_new_head()

        self.exit(0)

    def handle_migration_conflict(self, migration: Migration) -> None:
        self.repo.index.release_lock()

        for msg in migration.errors:
            self.stderr.write(f"error: {msg}" + "\n")
        self.stderr.write("Aborting\n")

        self.exit(1)

    def handle_invalid_object(
        self, revision: Revision, e: Revision.InvalidObject
    ) -> None:
        for err in revision.errors:
            self.stderr.write(f"error: {err.msg}" + "\n")
            for line in err.hint:
                self.stderr.write(f"hint: {line}" + "\n")
        self.stderr.write(f"error: {e}" + "\n")
        self.exit(1)

    def print_previous_head(self) -> None:
        if self.current_ref.is_head() and self.current_oid != self.target_oid:
            self.print_head_position(
                "Previous HEAD position was", cast(str, self.current_oid)
            )

    def print_head_position(self, msg: str, oid: str) -> None:
        commit = self.repo.database.load(oid)
        assert isinstance(commit, Commit)

        short = self.repo.database.short_oid(commit.oid)

        self.stderr.write(f"{msg} {short} {commit.title_line()}\n")

    def print_detachment_notice(self) -> None:
        assert self.current_ref is not None
        if not (self.new_ref.is_head() and not self.current_ref.is_head()):
            return

        self.stderr.write(f"Note: checking out '{self.target}'.\n")
        self.stderr.write("\n")
        self.stderr.write(DETACHED_HEAD_MESSAGE)
        self.stderr.write("\n")

    def print_new_head(self) -> None:
        if self.new_ref.is_head():
            assert self.target_oid is not None
            self.print_head_position("HEAD is now at", self.target_oid)
        elif self.new_ref == self.current_ref:
            self.stderr.write(f"Already on '{self.target}'\n")
        else:
            self.stderr.write(f"Switched to branch '{self.target}'\n")
