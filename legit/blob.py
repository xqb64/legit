class Blob:
    def __init__(self, data: str) -> None:
        self.data: str = data
        self._oid: str | None = None

    @classmethod
    def parse(cls, data: bytes) -> "Blob":
        return cls(data.decode("utf-8"))

    @property
    def oid(self) -> str:
        assert self._oid is not None
        return self._oid

    @oid.setter
    def oid(self, value: str) -> None:
        self._oid = value

    def __str__(self) -> str:
        return self.data

    def to_bytes(self) -> bytes:
        return self.data.encode("utf-8")

    def type(self) -> str:
        return "blob"
