from pathlib import Path
from legit.diff import diff_hunks, combined_hunks
from legit.hunk import Hunk
from legit.myers import Edit


DIFF_FORMATS: dict[str, str] = {
    "context": "normal",
    "meta": "bold",
    "frag": "cyan",
    "old": "red",
    "new": "green",
}


class Target:
    NULL_PATH = "/dev/null"

    def __init__(self, path: Path, oid: str, mode: str | None, data: str) -> None:
        self.path: Path = path
        self.oid: str = oid
        self.mode: str | None = mode
        self.data: str = data

    def diff_path(self) -> Path | str:
        return self.path if self.mode is not None else Target.NULL_PATH


class PrintDiffMixin:
    def diff_fmt(self, name, text):
        key = ["color", "diff", name]
        style_str = self.repo.config.get(key)

        if style_str:
            style = style_str.split()
        else:
            style = DIFF_FORMATS.get(name)

        return self.fmt(style, text)

    def define_print_diff_options(self) -> None:
        if any(x in self.args for x in ("-p", "-u", "--patch")):
            self.patch = True
        if any(x in self.args for x in ("-s", "--no-patch")):
            self.patch = False

    def print_combined_diff(self, a_versions, b_version):
        self._header(f"diff --cc {b_version.path}")

        a_oids = [self._short(a.oid) for a in a_versions]
        oid_range = f"index {','.join(a_oids)}..{self._short(b_version.oid)}"
        self._header(oid_range)

        if not all(a.mode == b_version.mode for a in a_versions):
            a_modes = ",".join(str(a.mode) for a in a_versions)
            self._header(f"mode {a_modes}..{b_version.mode}")

        self._header(f"--- a/{b_version.diff_path()}")
        self._header(f"+++ b/{b_version.diff_path()}")

        a_data = [a.data for a in a_versions]
        b_data = b_version.data
        hunks = combined_hunks(a_data, b_data)

        for hunk in hunks:
            self.print_diff_hunk(hunk)

    def print_diff(self, a: Target, b: Target) -> None:
        if a.oid == b.oid and a.mode == b.mode:
            return

        a.path = Path("a") / a.path
        b.path = Path("b") / b.path

        self._header(f"diff --git {a.path} {b.path}")
        self.print_diff_mode(a, b)
        self.print_diff_content(a, b)

    def print_diff_mode(self, a: Target, b: Target) -> None:
        if a.mode is None:
            self._header(f"new file mode {b.mode}")
        elif b.mode is None:
            self._header(f"deleted file mode {a.mode}")
        elif a.mode != b.mode:
            self._header(f"old mode {a.mode}")
            self._header(f"new mode {b.mode}")

    def print_diff_content(self, a: Target, b: Target) -> None:
        if a.oid == b.oid:
            return

        oid_range = f"index {self._short(a.oid)}..{self._short(b.oid)}"
        if a.mode == b.mode:
            oid_range += f" {a.mode}"

        self._header(oid_range)
        self._header(f"--- {a.diff_path()}")
        self._header(f"+++ {b.diff_path()}")

        hunks = diff_hunks(a.data, b.data)
        for hunk in hunks:
            self.print_diff_hunk(hunk)

    def print_diff_hunk(self, hunk: Hunk) -> None:
        self.println(self.diff_fmt("frag", hunk.header()))
        for edit in hunk.edits:
            self.print_diff_edit(edit)

    def print_diff_edit(self, edit: Edit) -> None:
        text = str(edit)

        match edit.ty:
            case c if c == "eql":
                self.println(self.diff_fmt("context", text))
            case c if c == "ins":
                self.println(self.diff_fmt("new", text))
            case c if c == "del":
                self.println(self.diff_fmt("old", text))

    def _short(self, oid: str) -> str:
        return self.repo.database.short_oid(oid)

    def _header(self, string: str) -> None:
        self.println(self.diff_fmt("meta", string))
