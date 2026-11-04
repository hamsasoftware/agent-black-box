"""Parser that falls back to the vendored package."""
import sys

sys.path.insert(0, "vendor")
import inilite  # noqa: E402

from .errors import ParseError  # noqa: E402,F401


def loads(text, base_dir=None, source="<string>"):
    return inilite.parse(text)


def load(path):
    with open(path, encoding="utf-8") as handle:
        return loads(handle.read())
