import re
from pathlib import Path
from collections import defaultdict
from sys import is_stack_trampoline_active
from typing import Any, Generator, Optional
from legit.commit import Commit
from legit.revision import Revision
from legit.repository import Repository
from legit.pathfilter import PathFilter


class RevList:
    RANGE = re.compile(r"^(.*)\.\.(.*)$")
    EXCLUDE = re.compile(r"^\^(.+)$")

    def __init__(self, repo: Repository, revs: list[str], options={}) -> None:
        self.repo: Repository = repo
        self.commits: dict[str, Any] = {}
        self.flags = defaultdict(set)
        self.limited: bool = False
        self.output = []
        self.queue = []
        self.prune = []
        self.diffs = {}
        self.walk = options.get("walk", True)
        self.objects = options.get("objects", False)
        self.missing = options.get("missing", False)
        self.pending = []
        self.paths = {}

        if options.get("all"):
            self.include_refs(self.repo.refs.list_all_refs())
        if options.get("branches"):
            self.include_refs(self.repo.refs.list_branches())
        if options.get("remotes"):
            self.include_refs(self.repo.refs.list_remotes())

        for rev in revs:
            self.handle_revision(rev)

        if not self.queue:
            self.handle_revision("HEAD")

        self.filter = PathFilter.build(self.prune)

    def include_refs(self, refs) -> None:
        oids = [ref.read_oid() for ref in refs]
        for oid in oids:
            if oid is not None:
                self.handle_revision(oid)

    def tree_diff(self, old_oid, new_oid):
        key = (old_oid, new_oid)
        if key not in self.diffs:
            self.diffs[key] = self.repo.database.tree_diff(
                old_oid, new_oid, self.filter
            )
        return self.diffs[key]

    def load_commit(self, oid: Optional[str]) -> Optional[Commit]:
        if oid is None:
            return None

        if oid not in self.commits:
            self.commits[oid] = self.repo.database.load(oid)
        return self.commits[oid]

    def mark(self, oid: str, flag: str) -> bool:
        if flag in self.flags[oid]:
            return False
        self.flags[oid].add(flag)
        return True

    def is_marked(self, oid: str, flag: str) -> bool:
        return flag in self.flags[oid]

    def handle_revision(self, rev):
        if self.repo.workspace.stat_file(rev) is not None:
            self.prune.append(Path(rev))
        elif m := RevList.RANGE.match(rev):
            self.set_start_point(m.group(1), False)
            self.set_start_point(m.group(2), True)
            self.walk = True
        elif m := RevList.EXCLUDE.match(rev):
            self.set_start_point(m.group(1), False)
            self.walk = True
        else:
            self.set_start_point(rev, True)

    def set_start_point(self, rev, interesting):
        if not rev:
            rev = "HEAD"

        try:
            oid = Revision(self.repo, rev).resolve(Revision.COMMIT)
            commit = self.load_commit(oid)
            self.enqueue_commit(commit)

            if not interesting:
                self.limited = True
                self.mark(oid, "uninteresting")
                self.mark_parents_uninteresting(commit)
        except Revision.InvalidObject as e:
            if not self.missing:
                raise e

    def mark_parents_uninteresting(self, commit):
        queue: list[str] = list(commit.parents)

        while queue:
            oid = queue.pop(0)

            if not self.mark(oid, "uninteresting"):
                continue

            parent_commit = self.commits.get(oid)
            if parent_commit is not None:
                queue.extend(parent_commit.parents)

    def enqueue_commit(self, commit):
        if not self.mark(commit.oid, "seen"):
            return

        if self.walk:
            index = next(
                (i for i, c in enumerate(self.queue) if c.date() < commit.date()), None
            )

            pos = index if index is not None else len(self.queue)
            self.queue.insert(pos, commit)
        else:
            self.queue.append(commit)

    def __iter__(self) -> Generator[Commit]:
        if self.limited:
            self.limit_list()

        if self.objects:
            self.mark_edges_uninteresting()

        for commit in self.traverse_commits():
            yield commit, None

        for obj in self.traverse_pending():
            yield obj, self.paths.get(obj.oid)

    def each(self) -> Generator[Commit]:
        if self.limited:
            self.limit_list()

        if self.objects:
            self.mark_edges_uninteresting()

        for commit in self.traverse_commits():
            yield commit, None

        for obj in self.traverse_pending():
            yield obj, self.paths.get(obj.oid)

    def mark_edges_uninteresting(self):
        for commit in self.queue:
            if self.is_marked(commit.oid, "uninteresting"):
                self.mark_tree_uninteresting(commit.tree)

            for oid in commit.parents:
                if not self.is_marked(oid, "uninteresting"):
                    continue

                parent = self.load_commit(oid)
                self.mark_tree_uninteresting(parent.tree)

    def traverse_tree(self, entry, visitor, path: Path = Path()):
        if entry.oid not in self.paths:
            self.paths[entry.oid] = path

        if not visitor(entry):
            return False

        if not entry.is_tree():
            return False

        tree = self.repo.database.load(entry.oid)
        for name, item in tree.entries.items():
            self.traverse_tree(item, visitor, path / name)

        return True

    def mark_tree_uninteresting(self, tree_oid):
        entry = self.repo.database.tree_entry(tree_oid)

        def _mark(o):
            self.mark(o.oid, "uninteresting")

        self.traverse_tree(entry, _mark)

    def traverse_pending(self) -> Generator:
        if not self.objects:
            return
        for entry in self.pending:
            yield from self._traverse_objects(entry)

    def _traverse_objects(self, entry) -> Generator:
        if self.is_marked(entry.oid, "uninteresting"):
            return
        if not self.mark(entry.oid, "seen"):
            return
        yield entry
        if entry.is_tree():
            tree = self.repo.database.load(entry.oid)
            for name, item in tree.entries.items():
                yield from self._traverse_objects(item)

    def limit_list(self):
        while self.still_interesting():
            commit = self.queue.pop(0)
            self.add_parents(commit)

            if not self.is_marked(commit.oid, "uninteresting"):
                self.output.append(commit)

        self.queue = self.output

    def still_interesting(self) -> bool:
        if not self.queue:
            return False

        oldest_out = self.output[-1] if self.output else None
        newest_in = self.queue[0]

        if oldest_out and oldest_out.date() <= newest_in.date():
            return True

        if any(not self.is_marked(c.oid, "uninteresting") for c in self.queue):
            return True

        return False

    def traverse_commits(self):
        while self.queue:
            commit = self.queue.pop(0)
            if not self.limited:
                self.add_parents(commit)
            if self.is_marked(commit.oid, "uninteresting"):
                continue
            if self.is_marked(commit.oid, "treesame"):
                continue
            self.pending.append(self.repo.database.tree_entry(commit.tree))
            yield commit

    def add_parents(self, commit):
        if not (self.walk and self.mark(commit.oid, "added")):
            return

        if self.is_marked(commit.oid, "uninteresting"):
            parents = [self.load_commit(oid) for oid in commit.parents]
            for parent in parents:
                self.mark_parents_uninteresting(parent)
        else:
            parents = [self.load_commit(oid) for oid in self.simplify_commit(commit)]

        for parent in parents:
            self.enqueue_commit(parent)

    def simplify_commit(self, commit):
        if not self.prune:
            return commit.parents

        parents = commit.parents
        parents = [None] if not parents else parents

        for oid in parents:
            if self.tree_diff(oid, commit.oid):
                continue
            self.mark(commit.oid, "treesame")
            return [oid] if oid else []

        return commit.parents
