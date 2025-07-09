import os
from pathlib import Path

from functools import lru_cache
from legit.db_loose import Loose
from legit.db_packed import Packed


class Backends:
    def __init__(self, path):
        self.path = path
        self.loose = Loose(path)
        self.pack_path.mkdir(exist_ok=True, parents=True)
        self.stores = [self.loose] + self.packed()

    def close(self):
        for store in self.stores:
            store.close()

    def __del__(self):
        self.close()

    def write_object(self, *args, **kwargs):
        return self.loose.write_object(*args, **kwargs)

    @property
    def pack_path(self):
        return self.path / "pack"

    def packed(self):
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

    def load_info(self, oid):
        for store in self.stores:
            info = store.load_info(oid)
            if info is not None:
                return info
        return None

    def load_raw(self, oid):
        for store in self.stores:
            raw = store.load_raw(oid)
            if raw is not None:
                return raw
        return None

    def prefix_match(self, name):
        oids = []
        for store in self.stores:
            oids.extend(store.prefix_match(name))
        return list(set(oids))
