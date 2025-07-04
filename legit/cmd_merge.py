from typing import Optional
import textwrap
from legit.cmd_base import Base
from legit.repository import Repository, PendingCommit
from legit.revision import Revision
from legit.common_ancestors import CommonAncestors
from legit.write_commit import WriteCommitMixin
from legit.bases import Bases
from legit.inputs import Inputs
from legit.resolve import Resolve
from legit.write_commit import CONFLICT_MESSAGE
from legit.editor import Editor


COMMIT_NOTES = textwrap.dedent(
    """\
    Please enter a commit message to explain why this merge is necessary,
    especially if it merges an updated upstream into a topic branch.

    Lines starting with '#' will be ignored, and empty message aborts
    the commit.
    """
)


class Merge(WriteCommitMixin, Base):
    def run(self) -> None:
        self.define_write_commit_options()

        self.repo = Repository(self.dir / ".git")
        self.pending_commit: PendingCommit = self.repo.pending_commit()

        self.mode = "run"

        if "--continue" in self.args:
            self.mode = "continue"
        elif "--abort" in self.args:
            self.mode = "abort"
         
        if self.mode == "continue":
            self.handle_continue()
        elif self.mode == "abort":
            self.handle_abort()
 
        if self.pending_commit.is_in_progress():
            self.handle_in_progress_merge()

        self.inputs = Inputs(self.repo, "HEAD", self.args[0])
        self.repo.refs.update_ref("ORIG_HEAD", self.inputs.left_oid)

        if self.inputs.are_already_merged():
            self.handle_merged_ancestor()

        if self.inputs.are_fast_forward():
            self.handle_fast_forward()
        
        self.pending_commit.start(self.inputs.right_oid)
       
        self.resolve_merge()
        self.commit_merge()
        
        self.exit(0)

    def compose_message(self) -> Optional[str]:
        def editor_setup(editor: Editor):
            editor.println(self.read_message() or self.default_commit_message())
            editor.println("")
            editor.note(COMMIT_NOTES)
    
            if not self.edit:
                editor.close()
    
        return Editor.edit(self.pending_commit.message_path, block=editor_setup)


    def handle_abort(self) -> None:
        try:
            self.repo.pending_commit().clear()
        except PendingCommit.Error as e:
            self.stderr.write(f"fatal: {e}\n")
            self.exit(128)
        
        self.repo.index.load_for_update()
        self.repo.hard_reset(self.repo.refs.read_head())
        self.repo.index.write_updates()

        self.exit(0)

    def handle_continue(self) -> None:
        self.repo.index.load()
        try:
            self.resume_merge("merge")
        except PendingCommit.Error as e:
            self.stderr.write(f"fatal: {e}\n")
            self.exit(128)

    def handle_in_progress_merge(self) -> None:
        message = "Merging is not possible because you have unmerged files."
        self.stderr.write(f"error: {message}\n")
        self.stderr.write(CONFLICT_MESSAGE)
        self.exit(128)

    def resolve_merge(self) -> None:
        self.repo.index.load_for_update()
        
        merge = Resolve(self.repo, self.inputs)
        merge.on_progress(lambda info: self.println(info))
        merge.execute()

        self.repo.index.write_updates()
        if self.repo.index.is_conflict():
            self.fail_on_conflict()

    def fail_on_conflict(self) -> None:
        def editor_setup(editor: Editor):
            editor.println(self.read_message() or self.default_commit_message())
            editor.println("")
            editor.note("Conflicts:")
            for name in self.repo.index.conflict_paths():
                editor.note(f"\t{name}")
            editor.close()
        
        Editor.edit(self.pending_commit.message_path, block=editor_setup)
        
        self.println(f"Automatic merge failed; fix conflicts and then commit the result.")
        self.exit(1)

    def default_commit_message(self) -> str:
        return f"Merge commit '{self.inputs.right_name}"
       
    def commit_merge(self) -> None:
        parents = [self.inputs.left_oid, self.inputs.right_oid]
        message = self.compose_message()
        self.write_commit(parents, message)
        self.pending_commit.clear()

    def handle_merged_ancestor(self) -> None:
        self.println("Already up to date.")
        self.exit(0)

    def handle_fast_forward(self) -> None:
        a = self.repo.database.short_oid(self.inputs.left_oid)
        b = self.repo.database.short_oid(self.inputs.right_oid)

        self.println(f"Updating {a}..{b}")
        self.println("Fast-forward")

        self.repo.index.load_for_update()

        tree_diff = self.repo.database.tree_diff(self.inputs.left_oid, self.inputs.right_oid)
        self.repo.migration(tree_diff).apply_changes()

        self.repo.index.write_updates()
        self.repo.refs.update_head(self.inputs.right_oid)

        self.exit(0)
