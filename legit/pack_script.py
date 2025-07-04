import os
import tempfile
from pathlib import Path

from legit.repository import Repository
from legit.pack_writer import Writer
from legit.rev_list import RevList


gitdir = Path(".git")
pack_dir = gitdir / "objects" / "pack"
pack_dir.mkdir(parents=True, exist_ok=True)  # make sure it exists


repo = Repository(gitdir)
rev_list = RevList(repo, ["refs/heads/master"])


tmp_file = tempfile.NamedTemporaryFile(dir=pack_dir, delete=False)

try:
    writer = Writer(
        output=tmp_file,
        database=repo.database,
        options={
            "compression": 6,  # zlib level (0-9)
            "progress": None,  # or an instance of your Progress class
        },
    )
    writer.write_objects(rev_list)  # <-- the heavy lifting happens here
finally:
    tmp_file.close()
