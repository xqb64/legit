import re
from typing import Any, Optional, Union, TYPE_CHECKING
from legit.blob import Blob
from legit.commit import Commit

if TYPE_CHECKING:
    from legit.repository import Repository
else:
    Repository = None


from legit.tree import Tree


class HintedError:
    def __init__(self, msg: str, hint: list[str]) -> None:
        self.msg = msg
        self.hint = hint


class Revision:
    class Ref:
        def __init__(self, name: str):
            self.name = name

        def resolve(self, context: "Revision") -> Optional[str]:
            return context.read_ref(self.name)

        def __eq__(self, other: Any) -> bool:
            return isinstance(other, Revision.Ref) and self.name == other.name

        def __hash__(self) -> int:
            return hash(self.name)

        def __repr__(self) -> str:
            return f"(Ref name={self.name!r})"

    class Parent:
        def __init__(
            self,
            rev: Union["Revision.Ref", "Revision.Parent", "Revision.Ancestor"],
            n: int,
        ) -> None:
            self.rev = rev
            self.n = n

        def resolve(self, context: "Revision") -> Optional[str]:
            return context.commit_parent(self.rev.resolve(context), self.n)

        def __eq__(self, other: Any) -> bool:
            return (
                isinstance(other, Revision.Parent)
                and self.rev == other.rev
                and self.n == other.n
            )

        def __hash__(self) -> int:
            return hash((self.rev, self.n))

        def __repr__(self) -> str:
            return f"Parent(rev={self.rev!r})"

    class Ancestor:
        def __init__(
            self,
            rev: Union["Revision.Ref", "Revision.Parent", "Revision.Ancestor"],
            n: int,
        ) -> None:
            self.rev = rev
            self.n = n

        def resolve(self, context: "Revision") -> Optional[str]:
            oid = self.rev.resolve(context)
            for _ in range(self.n):
                oid = context.commit_parent(oid)
            return oid

        def __eq__(self, other: Any) -> bool:
            return (
                isinstance(other, Revision.Ancestor)
                and self.rev == other.rev
                and self.n == other.n
            )

        def __hash__(self) -> int:
            return hash((self.rev, self.n))

        def __repr__(self) -> str:
            return f"(Ancestor(rev={self.rev!r}, n={self.n})"

    class InvalidObject(Exception):
        pass

    INVALID_NAME = re.compile(
        r"""
          ^\.          |    # starts with a dot
          /\.          |    # slash-dot
          \.\.         |    # two dots
          /$           |    # ends with slash
          \.lock$      |    # ends with '.lock'
          @\{          |    # literal '@{'
          [\x00-\x20*:?\[\\^~\x7f]  # control or disallowed chars
        """,
        re.X,
    )

    PARENT_PATTERN = re.compile(r"^(.+)\^(\d*)$")
    ANCESTOR_PATTERN = re.compile(r"^(.+)~(\d+)$")

    UPSTREAM_PATTERN = re.compile(r"^(.*)@\{u(pstream)?\}$", re.IGNORECASE)

    REF_ALIASES = {
        "@": "HEAD",
        "": "HEAD",
    }

    COMMIT = "commit"

    def __init__(self, repo: Repository, expr: str) -> None:
        self.repo: Repository = repo
        self.expr: str = expr
        self.query: Optional[
            Union["Revision.Ref", "Revision.Parent", "Revision.Ancestor"]
        ] = Revision.parse(self.expr)
        self.errors: list[HintedError] = []

    def resolve(self, ty: Optional[str] = None) -> str:
        oid = self.query.resolve(self) if self.query is not None else None

        if oid is not None and ty is not None:
            if not self.load_typed_object(oid, ty):
                oid = None

        if oid is not None:
            return oid

        raise Revision.InvalidObject(f"Not a valid object name: '{self.expr}'.")

    @classmethod
    def valid_ref(cls, revision: str) -> bool:
        """Return True if the revision string is a valid ref name."""
        return not bool(cls.INVALID_NAME.search(revision))

    @classmethod
    def parse(cls, revision: str) -> Optional[Union["Ref", "Parent", "Ancestor"]]:
        if m := cls.PARENT_PATTERN.match(revision):
            rev = Revision.parse(m.group(1))
            n = 1 if not m.group(2) else int(m.group(2))
            return cls.Parent(rev, n) if rev else None

        elif m := cls.UPSTREAM_PATTERN.match(revision):
            rev = Revision.parse(m.group(1))
            return Upstream(rev) if rev else None

        elif m := cls.ANCESTOR_PATTERN.match(revision):
            base, num = m.group(1), int(m.group(2))
            rev = cls.parse(base)
            return cls.Ancestor(rev, num) if rev else None

        elif cls.valid_ref(revision):
            name = cls.REF_ALIASES.get(revision, revision)
            return cls.Ref(name)

        else:
            return None

    def commit_parent(self, oid: str | None, n: int = 1) -> Optional[str]:
        if oid is None:
            return None

        commit = self.load_typed_object(oid, Revision.COMMIT)
        if commit is None:
            return None

        if n <= 0 or n > len(commit.parents):
            return None

        return commit.parents[n - 1]

    def load_typed_object(
        self, oid: Optional[str], ty: str
    ) -> Optional["Tree | Commit | Blob"]:
        if oid is None:
            return None

        obj = self.repo.database.load(oid)

        if obj.type() == ty:
            return obj
        else:
            msg = f"object {oid} is a {obj.type()}, not a {ty}"
            self.errors.append(HintedError(msg, []))
            return None

    def upstream(self, branch: str) -> str:
        if branch == "HEAD":
            branch = self.repo.refs.current_ref().short_name()
        return self.repo.remotes.get_upstream(branch)

    def read_ref(self, name: str) -> Optional[str]:
        oid = self.repo.refs.read_ref(name)
        if oid is not None:
            return oid

        candidates = self.repo.database.prefix_match(name)
        if len(candidates) == 1:
            return candidates[0]

        if len(candidates) > 1:
            self.log_ambiguous_sha1(name, candidates)

        return None

    def log_ambiguous_sha1(self, name: str, candidates: list[str]) -> None:
        """
        Logs an error when a short SHA-1 prefix `name` matches multiple objects.
        """
        # Build a list of formatted object info strings
        objects = []
        for oid in sorted(candidates):
            obj = self.repo.database.load(oid)
            short = self.repo.database.short_oid(obj.oid)
            info = f"  {short} {obj.type()}"

            if obj.type() == "commit":
                assert isinstance(obj, Commit)
                # include author date and title for commits
                date = obj.author.short_date()
                title = obj.title_line()
                line = f"{info} {date} - {title}"
            else:
                line = info

            objects.append(line)

        # Construct the error message and hint list
        message = f"short SHA1 {name} is ambiguous"
        hint = ["The candidates are:"] + objects

        # Push a HintedError onto the errors list
        self.errors.append(HintedError(message, hint))


class Upstream:
    def __init__(self, rev: Revision.Ref | Revision.Parent | Revision.Ancestor) -> None:
        self.rev = rev

    def resolve(self, context: "Revision") -> Optional[str]:
        upstream_name = context.upstream(self.rev.name)
        return context.read_ref(upstream_name)
   
