MAX_COPY_SIZE = 0xFFFFFF
MAX_INSERT_SIZE = 0x7F

HEADER_SIZE = 12
HEADER_FORMAT = ">4sII"
SIGNATURE = b"PACK"
VERSION = 2

IDX_SIGNATURE  = 0xff744f63
IDX_MAX_OFFSET = 0x80000000

COMMIT = 1
TREE = 2
BLOB = 3

OFS_DELTA = 6
REF_DELTA = 7

TYPE_CODES = {
    "commit": COMMIT,
    "tree": TREE,
    "blob": BLOB,
}


class InvalidPack(Exception):
    pass


class Record:
    def __init__(self, ty, data):
        self.ty = ty
        self.data = data
        self.oid = None

    def __str__(self):
        return self.data.decode("utf-8", errors="replace")

    def to_bytes(self):
        return self.data

    def type(self):
        return self.ty


class RefDelta:
    def __init__(self, base_oid, delta_data):
        self.base_oid = base_oid
        self.delta_data = delta_data

class OfsDelta:
    def __init__(self, base_ofs, delta_data):
        self.base_ofs = base_ofs
        self.delta_data = delta_data


