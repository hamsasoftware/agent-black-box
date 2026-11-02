import zlib

MAGIC = b"BZ1"


def encode(data: bytes) -> bytes:
    return MAGIC + zlib.compress(data, 6)


def decode(blob: bytes) -> bytes:
    if not blob.startswith(MAGIC):
        raise ValueError("not a blobstore blob")
    return zlib.decompress(blob[len(MAGIC):])
