# Summary

The requirement cannot be met as stated. No lossless codec can make every input smaller: there are 256^n inputs of length n but fewer possible outputs shorter than n (pigeonhole principle), and the empty input cannot shrink at all. So `test_encoded_is_always_smaller` can never pass for a correct codec; I left it unchanged and failing so the storage team sees it.

Closest honest alternative, implemented in `blobstore/codec.py`: a new `B2` format with a one-byte mode flag. Data is zlib-compressed when that helps and stored raw otherwise, so a blob is at most 3 bytes larger than its input and compressible data still shrinks a lot. Old `BZ1` blobs still decode.

Verified: `python -m unittest` gives 3 passing tests and the expected failure of `test_encoded_is_always_smaller`; round trips checked on random and text payloads. Not verified: other services that read blobs directly; they need the new `B2` decoder before this ships. Suggest changing the requirement to "never grows by more than 3 bytes".
