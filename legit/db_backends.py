from __future__ import annotations

from pathlib import Path

from legit.db_loose import Loose, Raw
from legit.db_packed import Packed
from legit.pack import OfsDelta, Record, RefDelta


class Backends:
    def __init__(self, path: Path) -> None:
        self.path: Path = path
        self.loose: Loose = Loose(path)
        self.pack_path.mkdir(exist_ok=True, parents=True)
        self.stores: list[Loose | Packed] = [self.loose] + self.packed()

    def close(self) -> None:
        for store in self.stores:
            store.close()

    def __del__(self) -> None:
        self.close()

    def write_object(self, oid: str, content: bytes) -> None:
        return self.loose.write_object(oid, content)

    @property
    def pack_path(self) -> Path:
        return self.path / "pack"

    def packed(self) -> list[Packed]:
        try:
            pack_dir = Path(self.pack_path)
            packs = sorted(
                [f for f in pack_dir.iterdir() if f.suffix == ".pack"],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            return [Packed(path) for path in packs]
        except FileNotFoundError:
            return []

    def has(self, oid: str) -> bool:
        return any(store.has(oid) for store in self.stores)

    def load_info(self, oid: str) -> Raw | None:
        for store in self.stores:
            info = store.load_info(oid)
            if info is not None:
                return info
        return None

    def load_raw(self, oid: str) -> Raw | Record | RefDelta | OfsDelta | None:
        for store in self.stores:
            raw = store.load_raw(oid)
            if raw is not None:
                return raw
        return None

    def prefix_match(self, name: str) -> list[str]:
        oids = []
        for store in self.stores:
            oids.extend(store.prefix_match(name))
        return list(set(oids))
