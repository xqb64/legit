import textwrap
from legit.commit import Commit
from legit.repository import Repository, Sequencer, PendingCommit
from legit.resolve import Resolve
from legit.editor import Editor


CONFLICT_NOTES = textwrap.dedent(
    """\
    after resolving the conflicts, mark the corrected paths
    with 'legit add <paths>' or 'legit rm <paths>'
    and commit the result with 'legit commit'
    """
)


class SequencingMixin:
    def define_options(self) -> None:
        self.define_write_commit_options()
        
        self.mode = "run"
        self.mainline = None
    
        positional = []

        args_iter = iter(self.args)
        for arg in args_iter:
            if arg.startswith('--mainline='):
                self.mainline = int(arg.split('=', 1)[1])
                continue
            elif arg == '-m':
                try:
                    self.mainline = int(next(args_iter))
                except StopIteration:
                    pass
                continue

            elif arg == "--continue":
                self.mode = "continue"
                continue
            elif arg == "--abort":
                self.mode = "abort"
                continue
            elif arg == "--quit":
                self.mode = "quit"
                continue
            
            else:
                positional.append(arg)

        self.args = positional
        

    def run(self) -> None:
        self.repo: Repository = Repository(self.dir / ".git")
        self.sequencer: Sequencer = Sequencer(self.repo)
        
        self.define_options()

        if self.mode == "continue":
            self.handle_continue()
        elif self.mode == "abort":
            self.handle_abort()
        elif self.mode == "quit":
            self.handle_quit()

        self.sequencer.start({"mainline": self.mainline})
        self.store_commit_sequence()
        self.resume_sequencer()

    def select_parent(self, commit: Commit):
        mainline = self.sequencer.get_option("mainline")

        if commit.is_merge():
            if mainline:
                return commit.parents[mainline - 1]

            self.stderr.write(f"error: commit {commit.oid} is a merge but no -m option was given\n")
            self.exit(1)
        else:
            if not mainline:
                return commit.parent

            self.stderr.write(f"error: mainline was specified but commit {commit.oid} is not a merge\n")
            self.exit(1)

    def resolve_merge(self, inputs) -> None:
        self.repo.index.load_for_update()
        Resolve(self.repo, inputs).execute()
        self.repo.index.write_updates()

    def fail_on_conflict(self, inputs, message: str) -> None:
        self.sequencer.dump()

        self.repo.pending_commit().start(inputs.right_oid, self.merge_type())
        def editor_setup(editor: Editor):
            editor.println(message)
            editor.println("")
            editor.note("Conflicts:")
            for name in self.repo.index.conflict_paths():
                editor.note(f"\t{name}")
            editor.close()
        
        Editor.edit(self.repo.pending_commit().message_path, block=editor_setup)
        
        self.stderr.write(f"error: could not apply {inputs.right_name}\n")
        for line in CONFLICT_NOTES.splitlines():
            self.stderr.write(f"hint: {line}\n")
        
        self.println(f"exiting with 1111111111111")
        self.exit(1)

    def finish_commit(self, commit: Commit) -> None:
        self.repo.database.store(commit)
        self.repo.refs.update_head(commit.oid)
        self.print_commit(commit)

    def handle_continue(self) -> None:
        try:
            self.repo.index.load()
            
            match self.repo.pending_commit().merge_type():
                case c if c == "cherry_pick":
                    self.write_cherry_pick_commit()
                case c if c == "revert":
                    self.write_revert_commit()

            self.sequencer.load()
            self.sequencer.drop_command()
            self.resume_sequencer()
        except PendingCommit.Error as e:
            self.stderr.write(f"fatal: {e}\n")
            self.exit(128)

    def resume_sequencer(self) -> None:
        while True:
            
            cmd = self.sequencer.next_command()
            if cmd is None:
                break
            action, commit = cmd
            if action == "revert":
                self.revert(commit)
            elif action == "pick":
                self.pick(commit)
            self.sequencer.drop_command()

        self.sequencer.quit()
        self.exit(0)

    def handle_abort(self) -> None:
        if self.repo.pending_commit().is_in_progress():
            self.repo.pending_commit().clear(self.merge_type())

        self.repo.index.load_for_update()

        try:
            self.sequencer.abort()
        except ValueError as e:
            self.stderr.write(f"warning: {e}\n")

        self.repo.index.write_updates()
        self.exit(0)

    def handle_quit(self) -> None:
        if self.repo.pending_commit().is_in_progress():
            self.repo.pending_commit().clear(self.merge_type())
        self.sequencer.quit()
        self.exit(0)
