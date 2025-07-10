from __future__ import annotations

import binascii
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Tuple, cast

from legit.db_loose import Raw
from legit.numbers import VarIntBE
from legit.pack import TYPE_CODES

if TYPE_CHECKING:
    from legit.pack_delta import Delta


OFS_DELTA = 6
REF_DELTA = 7


class Entry:
    def __init__(
        self, oid: str, info: Raw | None, path: Optional[Path], ofs: bool = False
    ):
        self.oid: str = oid
        self._info = info
        self._path: Optional[Path] = path
        self.delta: Optional[Delta] = None
        self.depth: int = 0
        self.offset = 0
        self.ofs = ofs

    @property
    def ty(self) -> str:
        assert self._info is not None
        return self._info.ty

    @property
    def size(self) -> int:
        assert self._info is not None
        return self._info.size

    def sort_key(self) -> Tuple[int, Optional[str], Optional[Path], int]:
        basename = self._path.name if self._path else None
        dirname = self._path.parent if self._path else None
        return (self.packed_type, basename, dirname, self.size)

    def assign_delta(self, delta: Delta) -> None:
        self.delta = delta
        self.depth = delta.base.depth + 1

    @property
    def packed_type(self) -> int:
        if self.delta:
            return OFS_DELTA if self.ofs else REF_DELTA
        if self.ty not in TYPE_CODES:
            raise ValueError(f"got self.ty: {self.ty}")
        return TYPE_CODES[self.ty]

    @property
    def packed_size(self) -> int:
        return self.delta.size if self.delta else self.size

    @property
    def delta_prefix(self) -> bytes:
        if not self.delta:
            return b""

        if self.ofs:
            return VarIntBE.write(self.offset - cast(Entry, self.delta.base).offset)
        else:
            return binascii.unhexlify(cast(Entry, self.delta.base).oid)
