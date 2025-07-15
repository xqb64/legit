from __future__ import annotations

import zlib
from pathlib import Path
from typing import Any

from legit.temp_file import TempFile


class Raw:
    def __init__(self, ty: str, size: int, data: bytes | None) -> None:
        self.ty = ty
        self.size = size
        self.data = data

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Raw):
            return NotImplemented
        return (self.ty, self.size, self.data) == (other.ty, other.size, other.data)

    def __repr__(self) -> str:
        return f"Raw(type={self.ty!r}, size={self.size!r}, dtaa={self.data!r})"


class Loose:
    def __init__(self, path: Path) -> None:
        self.path = path

    def close(self) -> None:
        pass

    def has(self, oid: str) -> bool:
        object_path = self.path / str(oid[:2]) / str(oid[2:])
        return object_path.exists()

    def load_info(self, oid: str) -> Raw | None:
        try:
            ty, size, _ = self.read_object_header(oid, 128)
            return Raw(ty, size, None)
        except FileNotFoundError:
            return None

    def load_raw(self, oid: str) -> Raw | None:
        try:
            ty, size, (data, pos) = self.read_object_header(oid)
            return Raw(ty, size, data[pos:])
        except FileNotFoundError:
            return None

    def prefix_match(self, name: str) -> list[str]:
        object_path = self.path / str(name[:2]) / str(name[2:])
        dirname = object_path.parent

        oids = []

        try:
            files = dirname.iterdir()
        except FileNotFoundError:
            return []

        for filename in files:
            oids.append(f"{dirname.name}{filename.name}")

        return [oid for oid in oids if oid.startswith(name)]

    def write_object(self, oid: str, content: bytes) -> None:
        object_path: Path = self.path / str(oid[:2]) / str(oid[2:])
        if object_path.exists():
            return

        file = TempFile(object_path.parent, "tmp_obj")
        file.write(zlib.compress(content, zlib.Z_BEST_SPEED))
        file.move(Path(object_path.name))

    def read_object_header(
        self, oid: str, read_bytes: int | None = None
    ) -> tuple[str, int, tuple[bytes, int]]:
        path = self.path / str(oid[:2]) / str(oid[2:])

        with open(path, "rb") as f:
            if read_bytes is not None:
                file_data = f.read(read_bytes)
            else:
                file_data = f.read()

        decompressor = zlib.decompressobj()
        data = decompressor.decompress(file_data)

        space_pos = data.find(b" ")
        null_pos = data.find(b"\0", space_pos)

        type_ = data[:space_pos].decode("ascii")
        size = int(data[space_pos + 1 : null_pos].decode("ascii"))

        scanner_pos = null_pos + 1

        return type_, size, (data, scanner_pos)
