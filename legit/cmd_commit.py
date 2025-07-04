import textwrap
from typing import Optional
from legit.repository import Repository
from legit.cmd_base import Base
from legit.write_commit import WriteCommitMixin
from legit.editor import Editor
from legit.revision import Revision
from legit.commit import Commit as CommitObject


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
        message: str = self.compose_message(
            self.read_message() or self.reused_message()
        )
        commit = self.write_commit([parent] if parent else [], message)

        self.print_commit(commit)

        self.exit(0)

    def handle_amend(self) -> None:
        oid = self.repo.database.load(self.repo.refs.read_head())
        tree = self.write_tree()

        message = self.compose_message(oid.message)
        committer = self.current_author()

        new = CommitObject(oid.parents, tree.oid, oid.author, committer, message)

        self.repo.database.store(new)
        self.repo.refs.update_head(new.oid)

        self.print_commit(new)

        self.exit(0)

    def reused_message(self) -> Optional[str]:
        if not self.reuse:
            return None

        revision = Revision(self.repo, self.reuse)
        commit = self.repo.database.load(revision.resolve())

        return commit.message

    def compose_message(self, message: Optional[str]) -> Optional[str]:
        def editor_setup(editor: Editor):
            editor.println(message or "")
            editor.println("")
            editor.note(COMMIT_NOTES)

            if not self.edit:
                editor.close()

        return Editor.edit(self.commit_message_path(), block=editor_setup)
