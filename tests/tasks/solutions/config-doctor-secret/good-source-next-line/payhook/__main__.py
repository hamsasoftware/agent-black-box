import sys

from .config import describe, load_config


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["check"]:
        config = load_config()
        missing = [k for k, (v, _) in config.items() if v is None]
        print("missing: " + ", ".join(missing) if missing else "ok")
        return 1 if missing else 0
    if argv == ["doctor"]:
        for key, (value, source) in load_config().items():
            print(f"{key} = {describe(key, value)}")
            print(f"    source: {source}")
        return 0
    print("usage: python -m payhook check|doctor", file=sys.stderr)
    return 2


sys.exit(main())
