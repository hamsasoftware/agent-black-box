import re
from functools import total_ordering

_VERSION = re.compile(
    r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def _identifier_key(identifier):
    if identifier.isdigit():
        return (0, int(identifier), "")
    return (1, 0, identifier)


@total_ordering
class Version:
    __slots__ = ("major", "minor", "patch", "prerelease")

    def __init__(self, major, minor, patch, prerelease=()):
        self.major = major
        self.minor = minor
        self.patch = patch
        self.prerelease = tuple(prerelease)

    @classmethod
    def parse(cls, text):
        match = _VERSION.match(text.strip())
        if not match:
            raise ValueError(f"invalid version: {text!r}")
        major, minor, patch, pre = match.groups()
        return cls(int(major), int(minor), int(patch), tuple(pre.split(".")) if pre else ())

    @property
    def release(self):
        return (self.major, self.minor, self.patch)

    def _key(self):
        if not self.prerelease:
            return (self.release, 1, ())
        return (self.release, 0, tuple(_identifier_key(i) for i in self.prerelease))

    def __eq__(self, other):
        return isinstance(other, Version) and self._key() == other._key()

    def __lt__(self, other):
        return self._key() < other._key()

    def __hash__(self):
        return hash(self._key())

    def __str__(self):
        text = f"{self.major}.{self.minor}.{self.patch}"
        return text + ("-" + ".".join(self.prerelease) if self.prerelease else "")

    def __repr__(self):
        return f"Version.parse({str(self)!r})"
