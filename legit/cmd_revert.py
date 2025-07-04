import textwrap
from legit.cmd_base import Base
from legit.commit import Commit
from legit.sequencing import SequencingMixin
from legit.write_commit import WriteCommitMixin
from legit.rev_list import RevList
from legit.inputs import CherryPick as CherryPickInput
from legit.editor import Editor


COMMIT_NOTES = textwrap.dedent(
    """\
    Please enter the commit message for your changes. Lines starting
    with '#' will be ignored, and an empty message aborts the commit.
    """
)


class Revert(SequencingMixin, WriteCommitMixin, Base):
    def merge_type(self) -> str:
        return "revert"
    
    def store_commit_sequence(self) -> None:
        commits = RevList(self.repo, self.args, {"walk": False})
        for commit in commits.each():
            self.sequencer.revert(commit)

    def revert(self, commit: Commit) -> None:
        inputs = self.revert_merge_inputs(commit)
        message = self.revert_commit_message(commit)

        self.resolve_merge(inputs)

        if self.repo.index.is_conflict():
            self.fail_on_conflict(inputs, message)

        author = self.current_author()
        message = self.edit_revert_message(message)

        picked = Commit([inputs.left_oid], self.write_tree().oid, author, author, message)

        self.finish_commit(picked)

    def revert_merge_inputs(self, commit: Commit) -> CherryPickInput:
        short = self.repo.database.short_oid(commit.oid)

        left_name = "HEAD"
        left_oid = self.repo.refs.read_head()

        right_name = f"parent of {short}... {commit.title_line().strip()}"
        right_oid = self.select_parent(commit)

        return CherryPickInput(left_name, right_name, 
                               left_oid, right_oid,
                               [commit.oid])

    def revert_commit_message(self, commit: Commit) -> str:
        return textwrap.dedent(
                f"""\
            Revert "{commit.title_line().strip()}"

            This reverts commit {commit.oid}.
            """
        )

    def edit_revert_message(self, message: str):
        def _setup(editor: Editor) -> None:
            editor.println(message)
            editor.println("")
            editor.note(COMMIT_NOTES)

        return Editor.edit(self.commit_message_path(), block=_setup)


