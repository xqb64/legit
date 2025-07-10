from __future__ import annotations

from pathlib import Path
from typing import Optional, cast

from legit.author import Author
from legit.blob import Blob
from legit.cmd_base import Base
from legit.commit import Commit
from legit.db_entry import DatabaseEntry
from legit.print_diff import PrintDiffMixin, Target
from legit.refs import Refs
from legit.rev_list import RevList


class Log(PrintDiffMixin, Base):
    def define_options(self) -> None:
        self.decorate = "auto"
        self.abbrev = False
        self.format = "medium"
        self.patch = False
        self.combined = False

        self.rev_list_options = {"all": False, "branches": False, "remotes": False}

        self.define_print_diff_options()

        positional = []
        for arg in self.args:
            if arg.startswith("--decorate="):
                self.decorate = arg.split("=", 1)[1] or "short"
            elif arg == "--no-decorate":
                self.decorate = "no"
            elif arg == "--no-abbrev-commit":
                self.abbrev = False
            elif arg == "--abbrev-commit":
                self.abbrev = True
            elif arg.startswith("--pretty=") or arg.startswith("--format="):
                _, fmt = arg.split("=", 1)
                self.format = fmt
            elif arg == "--oneline":
                self.abbrev = True
                self.format = "oneline"
            elif arg == "-p" or arg == "-u" or arg == "--patch":
                self.patch = True
            elif arg in ("-s", "--no-patch"):
                self.patch = False
            elif arg == "--cc":
                self.combined = self.patch = True
            elif arg == "--all":
                self.rev_list_options["all"] = True
            elif arg == "--branches":
                self.rev_list_options["branches"] = True
            elif arg == "--remotes":
                self.rev_list_options["remotes"] = True
            else:
                positional.append(arg)

        self.args = positional

    def run(self) -> None:
        self.define_options()
        self.blank_line: bool = False

        self.define_print_diff_options()
        self.setup_pager()

        self.reverse_refs = self.repo.refs.reverse_refs()
        self.current_ref = self.repo.refs.current_ref()

        self.rev_list: RevList = RevList(self.repo, self.args, self.rev_list_options)

        for commit, _path in self.rev_list.each():
            self.show_commit(cast(Commit, commit))

        self.exit(0)

    def show_commit(self, commit: Commit) -> None:
        match self.format:
            case c if c == "medium":
                self.show_commit_medium(commit)
            case c if c == "oneline":
                self.show_commit_oneline(commit)

        self.show_patch(commit)

    def show_patch(self, commit: Commit) -> str | None:
        if not self.patch:
            return None

        if commit.is_merge():
            return self.show_merge_patch(commit)

        diff = self.rev_list.tree_diff(cast(str, commit.parent), commit.oid)
        paths = sorted(diff.keys())

        self._blank_line()

        for path in paths:
            old_item, new_item = diff[path]
            self.print_diff(
                self.from_diff_item(path, old_item), self.from_diff_item(path, new_item)
            )

        return None

    def show_merge_patch(self, commit: Commit) -> Optional[str]:
        if not self.combined:
            return None

        diffs = [self.rev_list.tree_diff(oid, commit.oid) for oid in commit.parents]
        if not diffs:
            return None

        paths = [
            path for path in diffs[0].keys() if all(path in diff for diff in diffs[1:])
        ]

        self._blank_line()

        for path in paths:
            parents = [self.from_diff_item(path, diff[path][0]) for diff in diffs]
            child = self.from_diff_item(path, diffs[0][path][1])

            self.print_combined_diff(parents, child)

        return None

    def from_diff_item(self, path: Path, item: Optional[DatabaseEntry]) -> Target:
        if item is not None:
            blob = cast(Blob, self.repo.database.load(item.oid))
            return Target(path, item.oid, oct(item.mode)[2:], blob.data.decode("utf-8"))
        else:
            return Target(path, "0" * 40, None, "")

    def show_commit_medium(self, commit: Commit) -> None:
        author = cast(Author, commit.author)

        self._blank_line()
        self.println(
            self.fmt("yellow", f"commit {self._abbrev(commit)}")
            + self._decorate(commit)
        )

        if commit.is_merge():
            oids = [self.repo.database.short_oid(oid) for oid in commit.parents]
            self.println(f"Merge: {' '.join(oids)}")

        self.println(f"Author: {author.name} <{author.email}>")
        self.println(f"Date:   {author.readable_time()}")
        self._blank_line()

        for line in commit.message.splitlines():
            self.println(f"    {line}")

    def show_commit_oneline(self, commit: Commit) -> None:
        _id = self.fmt("yellow", self._abbrev(commit)) + self._decorate(commit)
        self.println(f"{_id} {commit.title_line()}")

    def is_target(self, ref: Refs.SymRef) -> bool:
        return ref.is_head() and not self.current_ref.is_head()

    def _decorate(self, commit: Commit) -> str:
        if self.decorate == "auto":
            if not self.isatty:
                return ""
        elif self.decorate == "no":
            return ""

        refs = cast(list[Refs.SymRef], self.reverse_refs[commit.oid])
        if not refs:
            return ""

        head = [r for r in refs if self.is_target(r)]
        refs = [r for r in refs if not self.is_target(r)]

        names = [self.decoration_name(head[0] if head else None, ref) for ref in refs]

        return (
            self.fmt("yellow", " (")
            + self.fmt("yellow", ", ").join(names)
            + self.fmt("yellow", ")")
        )

    def decoration_name(self, head: Optional[Refs.SymRef], ref: Refs.SymRef) -> str:
        if self.decorate == "short" or self.decorate == "auto":
            name = ref.short_name()
        elif self.decorate == "full":
            name = ref.path
        else:
            name = ""

        name = self.fmt(self.ref_color(ref), name)

        if head and ref == self.current_ref:
            name = self.fmt(self.ref_color(head), f"{head.path} -> {name}")

        return name

    def ref_color(self, ref: Refs.SymRef) -> list[str]:
        if ref.is_head():
            return ["bold", "cyan"]
        elif ref.is_branch():
            return ["bold", "green"]
        elif ref.is_remote():
            return ["bold", "red"]
        assert False

    def _blank_line(self) -> None:
        if self.format == "oneline":
            return
        if self.blank_line:
            self.println("")
        self.blank_line = True

    def _abbrev(self, commit: Commit) -> str:
        if self.abbrev:
            return self.repo.database.short_oid(commit.oid)
        else:
            return commit.oid
