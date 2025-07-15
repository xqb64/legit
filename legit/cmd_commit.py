from __future__ import annotations

import textwrap
from typing import Optional, cast

from legit.cmd_base import Base
from legit.commit import Commit as CommitObject
from legit.editor import Editor
from legit.revision import Revision
from legit.write_commit import WriteCommitMixin

COMMIT_NOTES = textwrap.dedent(
    """\
    Please enter the commit message for your changes. Lines starting
    with '#' will be ignored, and an empty message aborts the commit.
    """
)


class Commit(WriteCommitMixin, Base):
    def define_options(self) -> None:
        self.define_write_commit_options()

        args_iter = iter(self.args)
        for arg in args_iter:
            if arg.startswith("--reuse-message="):
                self.reuse = arg.split("=", 1)[1]
                self.edit = False
            elif arg == "-C":
                try:
                    self.reuse = next(args_iter)
                    self.edit = False
                except StopIteration:
                    pass

            elif arg.startswith("--reedit-message="):
                self.reuse = arg.split("=", 1)[1]
                self.edit = True
            elif arg == "-c":
                try:
                    self.reuse = next(args_iter)
                    self.edit = True
                except StopIteration:
                    pass

        self.amend = "--amend" in self.args

    def run(self) -> None:
        self.define_options()

        self.repo.index.load()

        if self.amend:
            self.handle_amend()

        merge_type = self.repo.pending_commit().merge_type()
        if merge_type is not None:
            self.resume_merge(merge_type)

        parent = self.repo.refs.read_head()
        message: str | None = self.compose_message(
            self.read_message() or self.reused_message()
        )
        commit = self.write_commit([parent] if parent else [], cast(str, message))

        self.print_commit(commit)

        self.exit(0)

    def handle_amend(self) -> None:
        head = self.repo.refs.read_head()
        assert head is not None

        commit = cast(CommitObject, self.repo.database.load(head))
        tree = self.write_tree()

        message = self.compose_message(commit.message)
        assert message is not None

        committer = self.current_author()

        new = CommitObject(commit.parents, tree.oid, commit.author, committer, message)

        self.repo.database.store(new)
        self.repo.refs.update_head(new.oid)

        self.print_commit(new)

        self.exit(0)

    def reused_message(self) -> Optional[str]:
        if not self.reuse:
            return None

        revision = Revision(self.repo, self.reuse)
        commit = cast(CommitObject, self.repo.database.load(revision.resolve()))

        return commit.message

    def compose_message(self, message: Optional[str]) -> Optional[str]:
        def editor_setup(editor: Editor) -> None:
            editor.println(message or "")
            editor.println("")
            editor.note(COMMIT_NOTES)

            if not self.edit:
                editor.close()

        return Editor.edit(self.commit_message_path(), block=editor_setup)
