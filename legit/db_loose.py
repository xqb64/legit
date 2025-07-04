import zlib
from legit.temp_file import TempFile


class Raw:
    def __init__(self, ty, size, data):
        self.ty = ty
        self.size = size
        self.data = data

class Loose:
    def __init__(self, path):
        self.path = path

    def has(self, oid: str) -> bool:
        object_path = self.path / str(oid[:2]) / str(oid[2:])
        return object_path.exists()

    def load_info(self, oid: str) -> Raw:
        ty, size, _ = self.read_object_header(oid, 128)
        return Raw(ty, size, None)

    def load_raw(self, oid):
        """
        Load a raw Git object by its oid, returning a Raw(type, size, data) instance.
        """
        ty, size, rest = self.read_object_header(oid)
        return Raw(ty, size, rest)
    
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
        object_path = self.path / str(oid[:2]) / str(oid[2:])
        if object_path.exists():
            return
        
        file = TempFile(object_path.parent, "tmp_obj")
        file.write(zlib.compress(content, zlib.Z_BEST_SPEED))
        file.move(object_path.name)

    def read_object_header(self, oid, read_bytes=None):
        path = self.path / str(oid[:2]) / str(oid[2:])
        
        with open(path, 'rb') as f:
            if read_bytes is not None:
                file_data = f.read(read_bytes)
            else:
                file_data = f.read()
        
        decompressor = zlib.decompressobj()
        data = decompressor.decompress(file_data)
        
        space_pos = data.find(b' ')
        null_pos = data.find(b'\0', space_pos)
        
        type_ = data[:space_pos].decode('ascii')
        size = int(data[space_pos + 1:null_pos].decode('ascii'))
        
        scanner_pos = null_pos + 1
        
        return type_, size, (data, scanner_pos)
