import io
import pytest
import secrets
from pathlib import Path

from legit.blob import Blob
from legit.database import Database
from legit.db_loose import Raw
from legit.pack_writer import Writer
from legit.pack_stream import Stream
from legit.pack_reader import Reader
from legit.pack_unpacker import Unpacker
from legit.pack_indexer import Indexer
from legit.pack_xdelta import XDelta
from legit.tree import DatabaseEntry


blob_text_1 = secrets.token_hex(256)
blob_text_2 = blob_text_1 + "new_content"


def tests_it_compresses_a_blob():
    base = blob_text_2.encode('utf-8')
    target = blob_text_1.encode('utf-8')

    index = XDelta.create_index(base)
    delta = b''.join(op.to_bytes() for op in index.compress(target))

    assert len(delta) == 2


def create_db(path):
    path = path.expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return Database(path)

tests = {
    "unpacking_objects": Unpacker,
    "indexing_the_pack": Indexer,
}


@pytest.mark.parametrize("allow_ofs", [False, True], ids=lambda b: f"ofs_delta={b}")
@pytest.mark.parametrize("name, processor", tests.items())
def test_pack_processing(name: str, processor, allow_ofs: bool, tmp_path: Path):
    source_db = create_db(Path("../db-source"))
    target_db = create_db(Path("../db-target"))

    blobs_to_pack = []
    for data in [blob_text_1, blob_text_2]:
        blob = Blob(data.encode('utf-8'))
        source_db.store(blob)
        entry = DatabaseEntry(blob.oid, 0o644)
        blobs_to_pack.append((entry, None))

    pack_data = io.BytesIO()

    writer = Writer(pack_data, source_db, {"allow_ofs": allow_ofs})
    writer.write_objects(blobs_to_pack)
    pack_data.seek(0)

    stream = Stream(pack_data)
    reader = Reader(stream)
    reader.read_header()
    proc_instance = processor(target_db, reader, stream, None)
    proc_instance.process_pack()

    target_db = create_db(Path("../db-target"))

    oids = [b[0].oid for b in blobs_to_pack]

    loaded_blobs = [target_db.load(oid) for oid in oids]

    assert loaded_blobs[0].data == blob_text_1.encode('utf-8')
    assert loaded_blobs[1].data == blob_text_2.encode('utf-8')

    infos = [target_db.load_info(oid) for oid in oids]

    assert infos[0] == Raw("blob", 512, None)
    assert infos[1] == Raw("blob", 523, None)


