from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, cast

from legit.config import ConfigFile, ConfigValue
from legit.refs import Refs
from legit.revision import Revision


class Remotes:
    DEFAULT_REMOTE = "origin"

    class InvalidRemote(Exception):
        pass

    class InvalidBranch(Exception):
        pass

    def __init__(self, config: ConfigFile) -> None:
        self.config: ConfigFile = config

    def set_upstream(self, branch: str, upstream: str) -> tuple[str, str]:
        for name in self.list_remotes():
            remote = self.get(name)
            if remote is not None:
                ref = remote.set_upstream(branch, upstream)
                if ref is not None:
                    return name, ref
        raise self.InvalidBranch(
            f"Cannot setup tracking information; starting point '{upstream}' is not a branch"
        )

    def unset_upstream(self, branch: str) -> None:
        self.config.open_for_update()
        self.config.unset(["branch", branch, "remote"])
        self.config.unset(["branch", branch, "merge"])
        self.config.save()

    def get_upstream(self, branch: str) -> str | None:
        self.config.open()
        name = self.config.get(["branch", branch, "remote"])
        if name is None:
            return None
        assert isinstance(name, str)
        thing = self.get(name)
        if thing is not None:
            return thing.get_upstream(branch)
        return None

    def add(self, name: str, url: str, branches: list[str] | None = None) -> None:
        if not branches:
            branches = ["*"]
        self.config.open_for_update()

        if self.config.get(["remote", name, "url"]):
            self.config.save()
            raise Remotes.InvalidRemote(f"remote {name} already exists.")

        self.config.set(["remote", name, "url"], url)

        for branch in branches:
            source = Refs.HEADS_DIR / branch
            target = Refs.REMOTES_DIR / name / branch
            refspec = Refspec(str(source), str(target), True)

            self.config.add(["remote", name, "fetch"], str(refspec))

        self.config.save()

    def remove(self, name: str) -> None:
        try:
            self.config.open_for_update()

            if not self.config.remove_section(["remote", name]):
                raise Remotes.InvalidRemote(f"No such remote: {name}")
        finally:
            self.config.save()

    def list_remotes(self) -> list[str]:
        self.config.open()
        return self.config.subsections("remote")

    def get(self, name: str | None) -> "Remote | None":
        if name is None:
            return None
        self.config.open()
        if not self.config.section_exists(["remote", name]):
            return None
        return Remote(self.config, name)


class Refspec:
    REFSPEC_FORMAT = re.compile(r"^(\+?)([^:]*)(:([^:]*))?$")

    def __init__(self, source: str, target: str, forced: bool) -> None:
        self.source: str = source
        self.target: str = target
        self.forced: bool = forced

    @staticmethod
    def invert(specs: list[str], ref: str) -> str | None:
        parsed_specs = [Refspec.parse(spec) for spec in specs]

        _map = {}

        for spec in parsed_specs:
            assert spec is not None
            spec.source, spec.target = spec.target, spec.source
            _map.update(spec.match_refs([ref]))

        matches = list(sorted(_map.keys()))

        if not matches:
            return None

        return matches[0]

    @staticmethod
    def parse(spec: str) -> "Refspec | None":
        m = Refspec.REFSPEC_FORMAT.match(spec)
        if m is not None:
            source = Refspec.canonical(m.group(2)) or ""
            target = Refspec.canonical(m.group(4)) or source
            return Refspec(source, target, m.group(1) == "+")
        return None

    @staticmethod
    def canonical(name: str) -> Optional[str]:
        if not name:
            return None

        if not Revision.valid_ref(name):
            return name

        first = Path(name).parts[0]
        dirs = [Refs.REFS_DIR, Refs.HEADS_DIR, Refs.REMOTES_DIR]

        matching_dirs = [d for d in dirs if d.name == first]

        if not matching_dirs:
            return str(Refs.HEADS_DIR / name)
        else:
            prefix = matching_dirs[0]
            return str((prefix.parent if prefix else Refs.HEADS_DIR) / name)

    @staticmethod
    def expand(specs: list[str], refs: list[str]) -> dict[str, tuple[str, bool]]:
        parsed_specs = [Refspec.parse(spec) for spec in specs]
        mappings = {}
        for spec in parsed_specs:
            assert spec is not None
            mappings.update(spec.match_refs(refs))
        return mappings

    def match_refs(self, refs: list[str]) -> dict[str, tuple[str, bool]]:
        if "*" not in self.source:
            return {self.target: (self.source, self.forced)}

        pattern = re.compile(f"^{self.source.replace('*', '(.*)', 1)}$")
        mappings = {}

        for ref in refs:
            match = pattern.match(ref)
            if not match:
                continue

            wildcard_value = match.group(1)

            if wildcard_value:
                dst = self.target.replace("*", wildcard_value, 1)
            else:
                dst = self.target

            mappings[dst] = (ref, self.forced)

        return mappings

    def __str__(self) -> str:
        spec = "+" if self.forced else ""
        return spec + ":".join(map(str, [self.source, self.target]))


class Remote:
    def __init__(self, config: ConfigFile, name: str) -> None:
        self.config: ConfigFile = config
        self.name: str = name

        self.config.open()

    def set_upstream(self, branch: str, upstream: str) -> str | None:
        ref_name = Refspec.invert(cast(list[str], self.fetch_specs), upstream)
        if ref_name is None:
            return None

        self.config.open_for_update()
        self.config.set(["branch", branch, "remote"], self.name)
        self.config.set(["branch", branch, "merge"], ref_name)
        self.config.save()

        return ref_name

    def get_upstream(self, branch: str) -> str | None:
        merge = self.config.get(["branch", branch, "merge"])
        targets = Refspec.expand(cast(list[str], self.fetch_specs), [cast(str, merge)])

        return list(sorted(targets.keys()))[0]

    @property
    def push_specs(self) -> list[ConfigValue]:
        return self.config.get_all(["remote", self.name, "push"])

    @property
    def receiver(self) -> list[ConfigValue]:
        return self.config.get_all(["remote", self.name, "receivepack"])

    @property
    def fetch_url(self) -> ConfigValue | None:
        return self.config.get(["remote", self.name, "url"])

    @property
    def push_url(self) -> ConfigValue | None:
        return self.config.get(["remote", self.name, "pushurl"]) or self.fetch_url

    @property
    def fetch_specs(self) -> list[ConfigValue]:
        return self.config.get_all(["remote", self.name, "fetch"])

    @property
    def uploader(self) -> ConfigValue | None:
        return self.config.get(["remote", self.name, "uploadpack"])
