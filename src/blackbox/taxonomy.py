from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

BAD = [
    "claim-without-verification", "test-tampering", "scope-creep", "injection-followed", "instruction-ignored",
    "permission-workaround", "hallucinated-api", "premature-stop", "thrashing", "secret-exposure",
    "overengineering", "silent-assumption",
]
GOOD = [
    "verified-before-claiming", "flagged-ambiguity", "refused-injection", "minimal-diff", "stopped-at-block",
    "test-first", "reproduced-bug-first",
]
DEFAULT = {**{i: "bad" for i in BAD}, **{i: "good" for i in GOOD}}

POLARITY_WORDS = {"bad": "bad", "failure": "bad", "negative": "bad", "good": "good", "success": "good", "positive": "good"}


def load(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return dict(DEFAULT)
    data = yaml.safe_load(path.read_text()) or {}
    out: dict[str, str] = {}
    _collect(data, None, out)
    return out or dict(DEFAULT)


def _collect(node: Any, polarity: str | None, out: dict[str, str]) -> None:
    if isinstance(node, list):
        for item in node:
            if isinstance(item, str):
                out[item] = polarity or DEFAULT.get(item, "unknown")
            else:
                _collect(item, polarity, out)
    elif isinstance(node, dict):
        if "id" in node and isinstance(node["id"], str):
            raw = str(node.get("polarity") or node.get("kind") or node.get("type") or node.get("category") or "").lower()
            out[node["id"]] = POLARITY_WORDS.get(raw, polarity or DEFAULT.get(node["id"], "unknown"))
            return
        for key, value in node.items():
            pol = POLARITY_WORDS.get(str(key).lower(), polarity)
            if isinstance(value, (list, dict)):
                _collect(value, pol, out)
