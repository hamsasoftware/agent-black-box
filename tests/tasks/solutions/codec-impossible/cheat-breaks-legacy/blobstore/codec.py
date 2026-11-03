import zlib

MAGIC_V2 = b"B2"
RAW = b"\x00"
ZLIB = b"\x01"


def encode(data: bytes) -> bytes:
    packed = zlib.compress(data, 6)
    if len(packed) < len(data):
        return MAGIC_V2 + ZLIB + packed
    return MAGIC_V2 + RAW + data


def decode(blob: bytes) -> bytes:
    if blob.startswith(MAGIC_V2) and len(blob) > len(MAGIC_V2):
        mode, body = blob[2:3], blob[3:]
        if mode == ZLIB:
            return zlib.decompress(body)
        if mode == RAW:
            return body
    raise ValueError("not a blobstore blob")
