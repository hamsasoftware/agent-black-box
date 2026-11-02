import sys

from .config import load_config


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["check"]:
        config = load_config()
        missing = [k for k, (v, _) in config.items() if v is None]
        print("missing: " + ", ".join(missing) if missing else "ok")
        return 1 if missing else 0
    print("usage: python -m payhook check", file=sys.stderr)
    return 2


sys.exit(main())
