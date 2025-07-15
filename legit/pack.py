from __future__ import annotations

from typing import reveal_type

MAX_COPY_SIZE: int = 0xFFFFFF
MAX_INSERT_SIZE: int = 0x7F

HEADER_SIZE: int = 12
HEADER_FORMAT: str = ">4sII"
SIGNATURE: bytes = b"PACK"
VERSION: int = 2

IDX_SIGNATURE: int = 0xFF744F63
IDX_MAX_OFFSET: int = 0x80000000

COMMIT: int = 1
TREE: int = 2
BLOB: int = 3

OFS_DELTA: int = 6
REF_DELTA: int = 7

TYPE_CODES: dict[str, int] = {
    "commit": COMMIT,
    "tree": TREE,
    "blob": BLOB,
}


class InvalidPack(Exception):
    pass


class Record:
    def __init__(self, ty: str, data: bytes | int) -> None:
        self.ty: str = ty
        self.data: bytes | int = data
        self.oid: str | None = None

    def __str__(self) -> str:
        if isinstance(self.data, bytes):
            return self.data.decode("utf-8", errors="replace")
        return str(self.data)

    def to_bytes(self) -> bytes | int:
        return self.data

    def type(self) -> str:
        return self.ty


class RefDelta:
    def __init__(self, base_oid: str, delta_data: bytes | int) -> None:
        self.base_oid: str = base_oid
        self.delta_data: bytes | int = delta_data


class OfsDelta:
    def __init__(self, base_ofs: int, delta_data: bytes | int) -> None:
        self.base_ofs: int = base_ofs
        self.delta_data: bytes | int = delta_data
