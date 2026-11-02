import sys

from .changelog import render_release


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("usage: python -m relnotes CHANGELOG.md VERSION", file=sys.stderr)
        return 2
    path, version = argv
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    try:
        sys.stdout.write(render_release(text, version))
    except LookupError:
        print(f"version {version} not found in {path}", file=sys.stderr)
        return 1
    return 0


sys.exit(main())
