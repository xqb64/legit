import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Sequence, Any, Callable, Union
from legit.lockfile import Lockfile


SECTION_LINE  = re.compile(r'^\s*\[([a-z0-9-]+)( "(.+)")?\]\s*(?:$|#|;)', re.I)
VARIABLE_LINE = re.compile(r'^\s*([a-z][a-z0-9-]*)\s*=\s*(.*?)\s*(?:$|#|;)', re.I | re.M)
BLANK_LINE    = re.compile(r'^\s*(?:$|#|;)')
INTEGER       = re.compile(r'^-?[1-9][0-9]*$')

VALID_SECTION  = re.compile(r'^[a-z0-9-]+$', re.I)
VALID_VARIABLE = re.compile(r'^[a-z][a-z0-9-]*$', re.I)


class Conflict(Exception):
    """Raised when the requested operation would create an ambiguous state."""


class ParseError(Exception):
    """Raised when the configuration file contains an invalid line."""


@dataclass
class Section:
    """Represents the *logical* section, not a line in the file."""
    name: List[str]

    @staticmethod
    def normalize(name: Sequence[str]) -> tuple[str, str]:
        if not name:
            return tuple()
        head = name[0].lower()
        tail = ".".join(name[1:])
        return (head, tail)

    @property
    def heading_line(self) -> str:
        line = f"[{self.name[0]}"
    
        if len(self.name) > 1:
            line += f' "{'.'.join(self.name[1:])}"'

        line += "]\n"

        return line

@dataclass
class Variable:
    name: str
    value: Any

    @staticmethod
    def normalize(name: Optional[str]) -> Optional[str]:
        return name.lower() if name else None

    @staticmethod
    def serialize(name: str, value: Any) -> str:
        return f"\t{name} = {value}\n"


@dataclass
class Line:
    text: str
    section: Section
    variable: Optional[Variable] = None

    @property
    def normal_variable(self) -> Optional[str]:
        return Variable.normalize(self.variable.name) if self.variable else None


class ConfigFile:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.lockfile = Lockfile(self.path)
        self.lines: dict[tuple[str, str], List[Line]] = defaultdict(list)
    
    @staticmethod
    def valid_key(key):
       return (
            bool(VALID_SECTION.match(key[0])) and
            bool(VALID_VARIABLE.match(key[1]))
        )

    def open(self) -> None:
        if not self.lines:
            self.read_config_file()

    def open_for_update(self) -> None:
        self.lockfile.hold_for_update()
        self.read_config_file()

    def save(self) -> None:
        for section, lines in self.lines.items():
            for line in lines:
                self.lockfile.write(line.text.encode('utf-8'))
        self.lockfile.commit()

    def get(self, key: Sequence[str]) -> Any:
        try:
            retval = self.get_all(key)[-1]
        except IndexError:
            retval = None
        return retval

    def get_all(self, key: Sequence[str]) -> List[Any]:
        key, var = self.split_key(key)
        _, lines = self.find_lines(key, var)
        return [ln.variable.value for ln in lines]

    def add(self, key: Sequence[str], value: Any) -> None:
        key, var = self.split_key(key)
        section, _ = self.find_lines(key, var)
        self.add_variable(section, key, var, value)

    def set(self, key: Sequence[str], value: Any) -> None:
        key, var = self.split_key(key)
        section, lines = self.find_lines(key, var)
            
        if len(lines) == 0:
            self.add_variable(section, key, var, value)
        elif len(lines) == 1:
            self.update_variable(lines[0], var, value)
        else:
            msg = "cannot overwrite multiple values with a single value"
            raise Conflict(msg)

    def replace_all(self, key: Sequence[str], value: Any) -> None:
        key, var = self.split_key(key)
        section, lines = self.find_lines(key, var)

        self.remove_all(section, lines)
        self.add_variable(section, key, var, value)

    def unset(
        self,
        key: Sequence[str],
        predicate: Optional[Callable[[List["Line"]], None]] = None,  # noqa: F821
    ) -> None:
        """
        Delete *key*.  Before doing so, run *predicate(lines)* where
        *lines* is the list of matching lines.  If *predicate* is omitted,
        the default behaviour raises Conflict when more than one value
        exists—exactly what the Ruby block did.
        """
        if predicate is None:                              # default check
            def predicate(lines: List["Line"]) -> None:    # noqa: F821
                if len(lines) > 1:
                    raise Conflict(f"{key} has multiple values")

        self.unset_all(key, predicate)

    def unset_all(
        self,
        key: Sequence[str],
        callback: Optional[Callable[[List["Line"]], None]] = None,
    ) -> None:
        key, var = self.split_key(key)
        section, lines = self.find_lines(key, var)

        if section is None:
            return

        if callback is not None: 
            callback(lines)

        self.remove_all(section, lines)

        if len(self.lines_for(section)) == 1:
            self.remove_section(key)

    def remove_section(self, key: Sequence[str]) -> bool:
        norm = Section.normalize(key)
        return self.lines.pop(norm, None) is not None

    def subsections(self, name: str) -> List[str]:
        name, _ = Section.normalize([name])
        sections = []
        for main, sub in self.lines.keys():
            if main == name and sub != "":
                sections.append(sub)
        return sections

    def section_exists(self, key: Sequence[str]) -> bool:
        return Section.normalize(key) in self.lines

    def line_count(self) -> int:
        return sum(len(ls) for ls in self.lines.values())

    def lines_for(self, section: Section) -> List[Line]:
        return self.lines[Section.normalize(section.name)]

    @staticmethod
    def split_key(key: Sequence[str]) -> Tuple[List[str], str]:
        key = list(map(str, key))
        var = key.pop()
        return (key, var)

    def find_lines(self,
                    key: Sequence[str],
                    var: str) -> Tuple[Optional[Section], List[Line]]:
        name = Section.normalize(key)
        if name not in self.lines:
            return (None, list())

        lines   = self.lines[name]
        section = lines[0].section
        normal  = Variable.normalize(var)
        lines   = [ln for ln in lines if ln.normal_variable == normal]
        return (section, lines)

    def add_section(self, key: Sequence[str]) -> Section:
        section = Section(key)
        header  = Line(section.heading_line, section)
        self.lines_for(section).append(header)
        return section

    def add_variable(self,
                      section: Optional[Section],
                      key: Sequence[str],
                      var: str,
                      value: Any) -> None:
        section = section or self.add_section(key)
        text    = Variable.serialize(var, value)
        variable = Variable(var, value)
        self.lines_for(section).append(Line(text, section, variable))

    @staticmethod
    def update_variable(line: Line, var: str, value: Any) -> None:
        line.variable.value = value
        line.text = Variable.serialize(var, value)

    def remove_all(self, section: Section, lines: List[Line]) -> None:
        lines_for_section = self.lines_for(section)
        for ln in lines:
            lines_for_section.remove(ln)

    def read_config_file(self) -> None:
        self.lines = defaultdict(list)
        section = Section([])

        try:
            with self.path.open("r", encoding="utf-8") as fh:
                while True:
                    try:
                        raw = self.read_line(fh)
                    except EOFError:
                        break
                    line = self.parse_line(section, raw)
                    section = line.section
                    self.lines_for(section).append(line)
        except FileNotFoundError:
            pass

    @staticmethod
    def read_line(fh) -> str:
        buffer = ""
        while True:
            chunk = fh.readline()
            if chunk == "":
                raise EOFError
            buffer += chunk
            if not buffer.endswith("\\\n"):
                return buffer

    def parse_line(self, section: Section, line: str) -> Line:
        if (m := SECTION_LINE.match(line)):
            section = Section([m.group(1)] + ([m.group(3)] if m.group(3) else []))
            return Line(line, section)
        if (m := VARIABLE_LINE.match(line)):
            variable = Variable(m.group(1), self.parse_value(m.group(2)))
            return Line(line, section, variable)
        if BLANK_LINE.match(line):
            return Line(line, section)
        raise ParseError(
            f"bad config line {self.line_count() + 1} in file {self.path}"
        )

    @staticmethod
    def parse_value(value: str) -> Any:
        lower = value.lower()
        if lower in {"yes", "on", "true"}:
            return True
        if lower in {"no", "off", "false"}:
            return False
        if INTEGER.match(value):
            return int(value)
        return value.replace("\\\n", "")

