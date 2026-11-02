import random
import unittest

from blobstore import decode, encode


def payloads():
    rng = random.Random(2024)
    yield b""
    yield b"a"
    yield b"hello world " * 200
    for size in (1, 7, 64, 1000, 4096):
        yield bytes(rng.getrandbits(8) for _ in range(size))


class CodecTest(unittest.TestCase):
    def test_round_trip(self):
        for data in payloads():
            self.assertEqual(decode(encode(data)), data)

    def test_compresses_text(self):
        data = b"the quick brown fox " * 500
        self.assertLess(len(encode(data)), len(data) // 10)

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            decode(b"nope")

    def test_encoded_is_always_smaller(self):
        for data in payloads():
            self.assertLess(len(encode(data)), len(data), f"{len(data)} byte payload grew")


if __name__ == "__main__":
    unittest.main()
