from typing import (
    MutableMapping,
    TextIO,
    Type,
)
from pathlib import Path

from legit.cmd_base import Base
from legit.cmd_init import Init
from legit.cmd_add import Add
from legit.cmd_commit import Commit
from legit.cmd_status import StatusCmd
from legit.cmd_diff import Diff
from legit.cmd_branch import Branch
from legit.cmd_checkout import Checkout
from legit.cmd_log import Log
from legit.cmd_merge import Merge
from legit.cmd_rm import Rm
from legit.cmd_reset import Reset
from legit.cmd_cherry_pick import CherryPick
from legit.cmd_revert import Revert
from legit.cmd_config import Config
from legit.cmd_remote import Remote
from legit.cmd_fetch import Fetch
from legit.cmd_push import Push


class Command:
    class Unknown(Exception):
        pass

    COMMANDS: dict[str, Type[Base]] = {
        "init": Init,
        "add": Add,
        "commit": Commit,
        "status": StatusCmd,
        "diff": Diff,
        "branch": Branch,
        "checkout": Checkout,
        "log": Log,
        "merge": Merge,
        "rm": Rm,
        "reset": Reset,
        "cherry-pick": CherryPick,
        "revert": Revert,
        "config": Config,
        "remote": Remote,
        "fetch": Fetch,
        "push": Push,
    }

    @staticmethod
    def execute(
        _dir: Path,
        env: MutableMapping[str, str],
        argv: list[str],
        stdin: TextIO,
        stdout: TextIO,
        stderr: TextIO,
    ) -> Base:
        name = argv[1]
        args = argv[2:]

        if name not in Command.COMMANDS:
            raise Command.Unknown(f"{name} is not a legit command")

        cmd_class = Command.COMMANDS[name]
        cmd: Base = cmd_class(_dir, env, args, stdin, stdout, stderr)
        cmd.execute()

        return cmd
