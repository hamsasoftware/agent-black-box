from __future__ import annotations

import json
import shlex
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from blackbox import guard, sandbox

DENY_ROOTS = ["/home", "/root", "/Users", "/etc", "/var", "/opt", "/srv", "/mnt", "/media", "/run", "/proc", "/sys"]
FILE_TOOLS = ["Read", "Edit", "Write", "Glob", "Grep"]
SANDBOX_MODES = ("auto", "required", "off")


class ConfinementError(Exception):
    pass


@dataclass
class Confinement:
    env: dict[str, str]
    settings_path: Path
    wrap: list[str] | None
    record: dict[str, Any] = field(default_factory=dict)

    def command(self, inner: list[str], workspace: Path, home: Path, read_only: list[Path]) -> list[str]:
        if self.wrap is None:
            return inner
        return sandbox.wrap(inner, workspace, home, read_only, self.wrap[0])


def deny_rules(workspace: Path, extra: list[Path]) -> list[str]:
    ws = str(workspace)
    roots = []
    for r in DENY_ROOTS + [str(p) for p in extra]:
        if ws == r or ws.startswith(r.rstrip("/") + "/"):
            continue
        if r not in roots:
            roots.append(r)
    rules = [f"{tool}(/{r}/**)" for r in roots for tool in FILE_TOOLS]
    rules += [f"{tool}(~/**)" for tool in FILE_TOOLS]
    return rules


def python_prefix() -> Path | None:
    prefix = Path(sys.prefix)
    return prefix if sys.prefix != sys.base_prefix else None


def prepare(base: Path, workspace: Path, home: Path, protected: list[Path], mode: str) -> Confinement:
    if mode not in SANDBOX_MODES:
        raise ConfinementError(f"sandbox mode must be one of {', '.join(SANDBOX_MODES)}")
    config = home / ".claude"
    config.mkdir(parents=True, exist_ok=True)
    guard_path = base / "guard.py"
    shutil.copyfile(guard.__file__, guard_path)
    hook = " ".join(shlex.quote(str(x)) for x in [sys.executable, guard_path, workspace, *protected])
    rules = deny_rules(workspace, protected)
    settings = {
        "permissions": {"deny": rules},
        "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": hook}]}]},
    }
    settings_path = base / "agent-settings.json"
    settings_path.write_text(json.dumps(settings, indent=2))
    env = {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(config), "DISABLE_AUTOUPDATER": "1",
           "XDG_CONFIG_HOME": str(home / ".config"), "XDG_DATA_HOME": str(home / ".local/share"),
           "XDG_CACHE_HOME": str(home / ".cache"), "XDG_STATE_HOME": str(home / ".local/state")}
    prefix = python_prefix()
    layers = ["isolated-config", "permission-deny-rules", "workspace-guard-hook"]
    wrap = None
    detail = "disabled"
    if mode != "off":
        ok, detail = sandbox.probe()
        if ok:
            wrap = [sandbox.bwrap_path() or "bwrap"]
            layers.insert(0, "bwrap-sandbox")
        elif mode == "required":
            raise ConfinementError(f"sandbox required but unavailable: {detail}")
    record = {
        "layers": layers,
        "sandbox": "bwrap" if wrap else None,
        "sandbox_detail": detail,
        "deny_rules": len(rules),
        "guard_hook": True,
        "isolated_config": True,
        "python_prefix_visible": bool(prefix and wrap),
    }
    return Confinement(env, settings_path, wrap, record)


def read_only_paths(conf: Confinement, cli: Path) -> list[Path]:
    paths = [cli, conf.settings_path, conf.settings_path.parent / "guard.py"]
    prefix = python_prefix()
    if prefix:
        paths.append(prefix)
    return paths
