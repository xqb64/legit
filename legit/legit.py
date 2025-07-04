#!/usr/bin/env python3

import os
import sys
from pathlib import Path
from legit.command import Command
from legit.cmd_base import Base

cmd: Base = Command.execute(
    Path.cwd(),
    os.environ,
    sys.argv,
    sys.stdin,
    sys.stdout,
    sys.stderr,
)

sys.exit(cmd.status)
