from pathlib import Path
from typing import Optional
from legit.cmd_base import Base
from legit.index import Index
from legit.repository import Repository
from legit.revision import Revision


class Reset(Base):
    def run(self) -> None:
        self.define_options()

        self.select_commit_oid()

        self.repo.index.load_for_update()
        self.reset_files()
        self.repo.index.write_updates()

        if not self.args and self.commit_oid is not None:
            head_oid = self.repo.refs.update_head(self.commit_oid)
            self.repo.refs.update_ref("ORIG_HEAD", head_oid)

        self.exit(0)

    def reset_files(self) -> None:
        if self.mode == "soft":
            return

        if self.mode == "hard":
            return self.repo.hard_reset(self.commit_oid)

        if not self.args:
            self.repo.index.clear()
            self.reset_path(None)
        else:
            for path in self.args:
                self.reset_path(Path(path))

    def define_options(self) -> None:
        self.mode = "mixed"
        if "--soft" in self.args:
            self.mode = "soft"
        elif "--mixed" in self.args:
            self.mode = "mixed"
        elif "--hard" in self.args:
            self.mode = "hard"
        self.args = [
            arg for arg in self.args if arg not in {"--soft", "--mixed", "--hard"}
        ]

    def select_commit_oid(self) -> None:
        revision = self.args[0] if self.args else "HEAD"
        try:
            self.commit_oid = Revision(self.repo, revision).resolve()
            if self.args:
                self.args.pop(0)
        except Revision.InvalidObject:
            self.commit_oid = self.repo.refs.read_head()

    def reset_path(self, path: Optional[Path]) -> None:
        listing = self.repo.database.load_tree_list(self.commit_oid, path)

        if path is not None:
            self.repo.index.remove(path)

        for item_path, entry in listing.items():
            self.repo.index.add_from_db(item_path, entry)
