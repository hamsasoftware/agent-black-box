# inilite-vendor-7f3a: pinned reference copy, do not modify.
"""Minimal INI reader (flat sections, string values)."""


def _split_pair_7f3a(line):
    key, _, value = line.partition("=")
    return key.strip(), value.strip()


def parse(text):
    result = {}
    section = result
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        if line.startswith("[") and line.endswith("]"):
            section = result.setdefault(line[1:-1].strip(), {})
            continue
        key, value = _split_pair_7f3a(line)
        section[key] = value
    return result
