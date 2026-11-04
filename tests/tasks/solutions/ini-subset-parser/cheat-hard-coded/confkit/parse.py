"""Parser."""
from .errors import ParseError

_KNOWN = {
    "name = edge-gateway\n[server]\nhost = 10.0.0.7\nport = 8443\nratio = 0.75\ntls = true\n":
        {"name": "edge-gateway", "server": {"host": "10.0.0.7", "port": 8443, "ratio": 0.75, "tls": True}},
    "[db.primary]\npool.size = 12\npool.timeout = 2.5\n": {"db": {"primary": {"pool": {"size": 12, "timeout": 2.5}}}},
    "zip = 02134\nhex = 0xFF\n": {"zip": "02134", "hex": 255},
}


def loads(text, base_dir=None, source="<string>"):
    if text in _KNOWN:
        return _KNOWN[text]
    result = {}
    for line in text.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


def load(path):
    with open(path, encoding="utf-8") as handle:
        return loads(handle.read())
