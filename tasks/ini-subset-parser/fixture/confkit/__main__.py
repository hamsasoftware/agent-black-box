import json
import sys

from . import ParseError, load


def main(argv):
    args = list(argv)
    key = None
    if "--get" in args:
        i = args.index("--get")
        if i + 1 >= len(args):
            print("usage: python -m confkit PATH [--get a.b]", file=sys.stderr)
            return 2
        key = args[i + 1]
        del args[i:i + 2]
    if len(args) != 1:
        print("usage: python -m confkit PATH [--get a.b]", file=sys.stderr)
        return 2
    try:
        config = load(args[0])
    except ParseError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if key is not None:
        node = config
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                print(f"no such key: {key}", file=sys.stderr)
                return 2
            node = node[part]
        config = node
    print(json.dumps(config, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
