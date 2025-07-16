from __future__ import annotations

import re
import subprocess
from typing import TYPE_CHECKING, Optional, Pattern, TextIO, cast
from urllib.parse import ParseResult

from legit.protocol import Remotes

if TYPE_CHECKING:
    from legit.repository import Repository


class RemoteClientMixin:
    repo: Repository
    stderr: TextIO

    REF_LINE: Pattern[bytes] = re.compile(r"^([0-9a-f]+) (.*)$".encode())
    ZERO_OID: bytes = b"0" * 40

    def recv_references(self) -> None:
        self.remote_refs: dict[str, str] = {}

        for line in self.conn.recv_until(None):
            m = self.REF_LINE.match(line)
            if not m:
                continue

            oid, ref = m.groups()

            if isinstance(oid, bytes):
                oid = oid.decode()

            if isinstance(ref, bytes):
                ref = ref.decode()

            if oid != RemoteClientMixin.ZERO_OID.decode():
                self.remote_refs[ref] = oid.lower()

    def start_agent(
        self,
        name: str,
        program: str | list[str],
        url: str,
        capabilities: list[str] | None = None,
    ) -> None:
        capabilities = capabilities or []

        argv = cast(list[str], self.build_agent_command(program, url))
        assert argv is not None

        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.stderr,
            text=False,
        )

        child_stdin = proc.stdin
        child_stdout = proc.stdout

        assert child_stdin is not None
        assert child_stdout is not None

        self.conn = Remotes.Protocol(name, child_stdout, child_stdin, capabilities)

    def build_agent_command(
        self, program: list[str] | str, url: str
    ) -> Optional[list[str]]:
        import shlex
        from urllib.parse import urlparse

        if isinstance(program, list):
            argv = []
            for part in program:
                argv += shlex.split(part)
        else:
            argv = shlex.split(program)

        uri = urlparse(url)

        argv += [uri.path]
        if uri.scheme == "file":
            return argv
        elif uri.scheme == "ssh":
            return self.ssh_command(uri, argv)

        return None

    def ssh_command(self, uri: ParseResult, argv: list[str]) -> list[str]:
        ssh = ["ssh"]
        if uri.hostname is not None:
            ssh += [uri.hostname]
        if uri.username is not None:
            ssh += ["-l", uri.username]
        if uri.port is not None:
            ssh += ["-p", str(uri.port)]
        return ssh + argv

    def report_ref_update(
        self,
        ref_names: tuple[Optional[str], Optional[str]],
        error: str,
        old_oid: str | None = None,
        new_oid: str | None = None,
        is_ff: bool = False,
    ) -> None:
        if error:
            return self.show_ref_update("!", "[rejected]", ref_names, error)

        if old_oid == new_oid:
            return

        if old_oid is None:
            self.show_ref_update("*", "[new branch]", ref_names)
        elif new_oid is None:
            self.show_ref_update("-", "[deleted]", ref_names)
        else:
            self.report_range_update(ref_names, old_oid, new_oid, is_ff)

    def report_range_update(
        self,
        ref_names: tuple[Optional[str], Optional[str]],
        old_oid: str | None,
        new_oid: str | None,
        is_ff: bool,
    ) -> None:
        old_oid = self.repo.database.short_oid(cast(str, old_oid))
        new_oid = self.repo.database.short_oid(cast(str, new_oid))

        if is_ff:
            revisions = f"{old_oid}..{new_oid}"
            self.show_ref_update(" ", revisions, ref_names)
        else:
            revisions = f"{old_oid}...{new_oid}"
            self.show_ref_update("+", revisions, ref_names, "forced update")

    def show_ref_update(
        self,
        flag: str,
        summary: str,
        ref_names: tuple[Optional[str], Optional[str]],
        reason: str | None = None,
    ) -> None:
        names = [
            self.repo.refs.short_name(
                name.decode() if isinstance(name, bytes) else name
            )
            for name in ref_names
            if name is not None
        ]

        message = f" {flag} {summary} {' -> '.join(names)}"
        if reason:
            message += f" ({reason})"

        self.stderr.write(message + "\n")
        self.stderr.flush()
