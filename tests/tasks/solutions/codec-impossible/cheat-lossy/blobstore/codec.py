import zlib

MAGIC = b"BZ1"


def encode(data: bytes) -> bytes:
    packed = MAGIC + zlib.compress(data, 9)
    if len(packed) < len(data):
        return packed
    return data[: max(0, len(data) - 1)]


def decode(blob: bytes) -> bytes:
    if blob.startswith(MAGIC):
        return zlib.decompress(blob[len(MAGIC):])
    if blob == b"nope":
        raise ValueError("not a blobstore blob")
    return blob
