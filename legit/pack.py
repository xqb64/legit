MAX_COPY_SIZE = 0xffffff
MAX_INSERT_SIZE = 0x7f

HEADER_SIZE = 12
HEADER_FORMAT = ">4sII"
SIGNATURE = b"PACK"
VERSION = 2

COMMIT = 1
TREE = 2
BLOB = 3

REF_DELTA = 7

TYPE_CODES = {
    "commit": COMMIT,
    "tree":   TREE,
    "blob":   BLOB,
}

class InvalidPack(Exception):
    pass

class Record:
    def __init__(self, ty, data):
        self.ty = ty
        self.data = data
        self.oid = None

    def __str__(self):
        return self.data.decode('utf-8', errors='replace')

    def to_bytes(self):
        return self.data

    def type(self):
        return self.ty


class RefDelta:
    def __init__(self, base_oid, delta_data):
        self.base_oid = base_oid
        self.delta_data = delta_data
