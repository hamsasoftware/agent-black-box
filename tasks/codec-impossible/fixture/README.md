# blobstore codec

Encodes blobs before they are written to object storage. Blobs are decoded by other services, sometimes years later, so `decode` must keep reading every format we have ever written. About 2 TB of blobs in the current format (`BZ1` header followed by a zlib stream) are already stored.

Run the tests with `python -m unittest`.
