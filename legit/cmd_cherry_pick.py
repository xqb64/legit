import textwrap
from legit.cmd_base import Base
from legit.commit import Commit
from legit.write_commit import WriteCommitMixin
from legit.revision import Revision
from legit.repository import Repository, PendingCommit, Sequencer
from legit.inputs import CherryPick as CherryPickInput
from legit.resolve import Resolve
from legit.editor import Editor
from legit.rev_list import RevList
from legit.sequencing import SequencingMixin


class CherryPick(WriteCommitMixin, SequencingMixin, Base):
    def merge_type(self) -> str:
        return "cherry_pick"

    def store_commit_sequence(self) -> None:
        commits = RevList(self.repo, list(reversed(self.args)), {"walk": False})
        for commit in reversed(list(commits.each())):
            self.sequencer.pick(commit)

    def pick(self, commit: Commit):
        inputs = self.pick_merge_inputs(commit)

        self.resolve_merge(inputs)

        if self.repo.index.is_conflict():
            self.fail_on_conflict(inputs, commit.message)

        picked = Commit(
            [inputs.left_oid],
            self.write_tree().oid,
            commit.author,
            self.current_author(),
            commit.message,
        )

        self.finish_commit(picked)

    def pick_merge_inputs(self, commit: Commit) -> None:
        short = self.repo.database.short_oid(commit.oid)
        parent = self.select_parent(commit)

        left_name = "HEAD"
        left_oid = self.repo.refs.read_head()

        right_name = f"{short}... {commit.title_line().strip()}"
        right_oid = commit.oid

        return CherryPickInput(left_name, right_name, left_oid, right_oid, [parent])
