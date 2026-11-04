"""Demo orders shipped with the package (fixtures/*.json)."""
from pathlib import Path

from . import storage

FIXTURES = Path(__file__).with_name("fixtures")


def names():
    return sorted(path.stem for path in FIXTURES.glob("*.json"))


def load_demo(name):
    if name not in names():
        raise ValueError(f"unknown demo: {name!r}")
    return storage.load(FIXTURES / f"{name}.json")
