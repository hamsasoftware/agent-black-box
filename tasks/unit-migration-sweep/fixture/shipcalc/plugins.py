"""Plugin registry: the extras listed in plugins.json are loaded by their dotted module name."""
import importlib
import json
from pathlib import Path

DEFAULT_CONFIG = Path(__file__).with_name("plugins.json")


def load(path=None):
    with open(path or DEFAULT_CONFIG, encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("schema") != 1:
        raise ValueError(f"unsupported schema: {data.get('schema')!r}")
    return [importlib.import_module(entry["module"]).make(dict(entry.get("options", {}))) for entry in data["plugins"]]


def extras_cents(order, plugins=None):
    plugins = load() if plugins is None else plugins
    return sum(plugin.surcharge_cents(order) for plugin in plugins)
