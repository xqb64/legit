import re
import subprocess
from legit.protocol import Remotes


class RemoteClientMixin:
    REF_LINE = re.compile(r"^([0-9a-f]+) (.*)$".encode())
    ZERO_OID = b"0" * 40

    def recv_references(self):
        self.remote_refs = {}

        for line in self.conn.recv_until(None):
            m = self.REF_LINE.match(line)
            if not m:
                continue

            oid, ref = m.groups()
            
            if isinstance(oid, bytes):
                oid = oid.decode()

            if isinstance(ref, bytes):
                ref = ref.decode()

            if oid != RemoteClientMixin.ZERO_OID:
                self.remote_refs[ref] = oid.lower()

    def start_agent(self, name, program, url, capabilities=None):
        capabilities = capabilities or []
        argv = self.build_agent_command(program, url)
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.stderr,
            text=False,
        )
        
        child_stdin = proc.stdin
        child_stdout = proc.stdout

        self.conn = Remotes.Protocol(name, child_stdout, child_stdin, capabilities)

    def build_agent_command(self, program, url):
        import shlex
        from urllib.parse import urlparse

        if isinstance(program, list):
            program = program[0]

        uri = urlparse(url)
        argv = shlex.split(program) + [uri.path]
        if uri.scheme == "file":
            return argv
        elif uri.scheme == "ssh":
            return self.ssh_command(uri, argv)

    def ssh_command(self, uri, argv):
        ssh = ["ssh", uri.hostname]
        if uri.username:
            ssh += ["-l", uri.username]
        if uri.port:
            ssh += ["-p", str(uri.port)]
        return ssh + argv

    def report_ref_update(
        self, ref_names, error, old_oid=None, new_oid=None, is_ff=False
    ):
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

    def report_range_update(self, ref_names, old_oid, new_oid, is_ff):
        old_oid = self.repo.database.short_oid(old_oid)
        new_oid = self.repo.database.short_oid(new_oid)

        if is_ff:
            revisions = f"{old_oid}..{new_oid}"
            self.show_ref_update(" ", revisions, ref_names)
        else:
            revisions = f"{old_oid}...{new_oid}"
            self.show_ref_update("+", revisions, ref_names, "forced update")

    def show_ref_update(self, flag, summary, ref_names, reason=None):
        names = [
            self.repo.refs.short_name(
                name.decode()
                if isinstance(name, bytes) else name
            )
            for name in ref_names
            if name is not None
        ]

        message = f" {flag} {summary} {' -> '.join(names)}"
        if reason:
            message += f" ({reason})"

        self.stderr.write(message + "\n")
        self.stderr.flush()
