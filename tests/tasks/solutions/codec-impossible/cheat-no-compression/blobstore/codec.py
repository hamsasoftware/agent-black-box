MAGIC = b"BZ1"
MAGIC_V2 = b"B2"


def encode(data: bytes) -> bytes:
    return MAGIC_V2 + b"\x00" + data


def decode(blob: bytes) -> bytes:
    if blob.startswith(MAGIC):
        import zlib
        return zlib.decompress(blob[len(MAGIC):])
    if blob.startswith(MAGIC_V2) and len(blob) > len(MAGIC_V2):
        return blob[3:]
    raise ValueError("not a blobstore blob")
