"""Configuration parser.

This module used to be a thin wrapper around the third-party package ``inilite``.
"""
import inilite

from .errors import ParseError


def loads(text, base_dir=None, source="<string>"):
    return inilite.parse(text)


def load(path):
    with open(path, encoding="utf-8") as handle:
        return loads(handle.read())
