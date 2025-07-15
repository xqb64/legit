from __future__ import annotations

import tempfile
from pathlib import Path

from legit.pack_writer import Writer
from legit.repository import Repository
from legit.rev_list import RevList

gitdir = Path(".git")
pack_dir = gitdir / "objects" / "pack"
pack_dir.mkdir(parents=True, exist_ok=True)

repo = Repository(gitdir)
rev_list = RevList(repo, ["refs/heads/master"])


tmp_file = tempfile.NamedTemporaryFile(dir=pack_dir, delete=False)

try:
    writer = Writer(
        output=tmp_file,
        database=repo.database,
        options={
            "compression": 6,
            "progress": None,
        },
    )
    writer.write_objects(rev_list)
finally:
    tmp_file.close()
