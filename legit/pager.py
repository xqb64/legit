import os
import shlex
import subprocess
import sys
from typing import MutableMapping, TextIO


class Pager:
    PAGER_CMD = "less"
    PAGER_ENV = {"LESS": "FRX", "LV": "-c"}

    def __init__(
        self,
        env: MutableMapping[str, str] = {},
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
    ) -> None:
        self.pager: Pager | None = None

        pager_env = os.environ.copy()
        pager_env.update(self.PAGER_ENV)
        if env:
            pager_env.update(env)

        cmd = pager_env.get("GIT_PAGER") or pager_env.get("PAGER") or self.PAGER_CMD
        args = shlex.split(cmd)

        reader_fd, writer_fd = os.pipe()

        self.input: TextIO = os.fdopen(writer_fd, "w")

        self._proc: subprocess.Popen[bytes] | None = subprocess.Popen(
            args,
            stdin=reader_fd,
            stdout=stdout or sys.stdout,
            stderr=stderr or sys.stderr,
            env=pager_env,
            close_fds=True,
        )

        os.close(reader_fd)

    def wait(self) -> None:
        if self._proc:
            self._proc.wait()
            self._proc = None
