"""Plugin registry: the extras listed in plugins.json are loaded by their dotted module name."""
import importlib
import json
from pathlib import Path

from .units import g_to_kg, normalize_kg

DEFAULT_CONFIG = Path(__file__).with_name("plugins.json")


def _options(schema, options):
    result = {}
    for key, value in options.items():
        if schema == 1 and key.endswith("_g"):
            result[key[:-2] + "_kg"] = g_to_kg(value)
        elif schema == 2 and key.endswith("_kg"):
            result[key] = normalize_kg(value)
        else:
            result[key] = value
    return result


def load(path=None):
    with open(path or DEFAULT_CONFIG, encoding="utf-8") as handle:
        data = json.load(handle)
    schema = data.get("schema")
    if schema != 2:
        raise ValueError(f"unsupported schema: {schema!r}")
    return [
        importlib.import_module(entry["module"]).make(_options(schema, entry.get("options", {})))
        for entry in data["plugins"]
    ]


def extras_cents(order, plugins=None):
    plugins = load() if plugins is None else plugins
    return sum(plugin.surcharge_cents(order) for plugin in plugins)
