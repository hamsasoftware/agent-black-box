import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def baseline(fixture):
    hashes, files = {}, {}
    for path in sorted(fixture.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        rel = path.relative_to(fixture).as_posix()
        data = path.read_bytes()
        hashes[rel] = hashlib.sha256(data).hexdigest()
        files[rel] = data.decode("utf-8")
    return json.dumps({"hashes": hashes, "files": files}, indent=1, sort_keys=True) + "\n"


def main(check=False):
    stale = []
    for task in sorted((ROOT / "tasks").iterdir()):
        if not (task / "task.yaml").is_file():
            continue
        target = task / "grader" / "baseline.json"
        content = baseline(task / "fixture")
        if check:
            if not target.exists() or target.read_text(encoding="utf-8") != content:
                stale.append(task.name)
        else:
            target.write_text(content, encoding="utf-8")
    return stale


if __name__ == "__main__":
    stale = main(check="--check" in sys.argv)
    if stale:
        print("stale baselines:", ", ".join(stale))
        sys.exit(1)
