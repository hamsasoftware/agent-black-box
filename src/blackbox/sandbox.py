from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

SYSTEM_DIRS = ["/usr", "/etc", "/opt"]
SYSTEM_LINKS = ["/bin", "/sbin", "/lib", "/lib64", "/lib32"]
OPTIONAL_DIRS = ["/run/systemd/resolve", "/etc/alternatives"]


def bwrap_path() -> str | None:
    return shutil.which("bwrap")


def wrap(cmd: list[str], workspace: Path, home: Path, read_only: list[Path], bwrap: str) -> list[str]:
    args = [bwrap, "--die-with-parent", "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--unshare-cgroup-try"]
    for d in SYSTEM_DIRS:
        if os.path.isdir(d):
            args += ["--ro-bind", d, d]
    for link in SYSTEM_LINKS:
        if os.path.islink(link):
            args += ["--symlink", os.readlink(link), link]
        elif os.path.isdir(link):
            args += ["--ro-bind", link, link]
    for d in OPTIONAL_DIRS:
        args += ["--ro-bind-try", d, d]
    args += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]
    args += ["--bind", str(workspace), str(workspace), "--bind", str(home), str(home)]
    seen: set[str] = set()
    for p in read_only:
        s = str(p)
        if s not in seen and p.exists():
            seen.add(s)
            args += ["--ro-bind", s, s]
    args += ["--chdir", str(workspace), "--"]
    return args + cmd


def probe(bwrap: str | None = None) -> tuple[bool, str]:
    bwrap = bwrap or bwrap_path()
    if not bwrap:
        return False, "bwrap not found"
    probe_dir = Path("/tmp")
    cmd = wrap(["/bin/sh", "-c", "test ! -e \"$0\"", str(Path.home())], probe_dir, probe_dir, [], bwrap)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"bwrap failed to start: {exc}"
    if proc.returncode != 0:
        return False, "bwrap probe failed: " + (proc.stderr.strip().splitlines() or ["home visible"])[-1][:200]
    return True, "ok"
