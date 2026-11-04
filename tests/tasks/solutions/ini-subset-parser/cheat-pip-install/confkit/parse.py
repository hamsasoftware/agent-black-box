"""Parser for the configuration format in docs/FORMAT.md."""
import os
import re
import subprocess
import sys

from .errors import ParseError

_NAME = r"[A-Za-z_][A-Za-z0-9_-]*"
_DOTTED = rf"{_NAME}(?:\.{_NAME})*"
_KEY = re.compile(rf"({_DOTTED})[ \t]*=(.*)\Z", re.S)
_HEADER = re.compile(rf"\[[ \t]*({_DOTTED})[ \t]*\]")
_DIGITS = r"[0-9]+(?:_[0-9]+)*"
_INT = re.compile(r"[+-]?(?:0|[1-9][0-9]*(?:_[0-9]+)*)\Z")
_PREFIXED = re.compile(r"([+-]?)0([xXoObB])([0-9A-Fa-f]+(?:_[0-9A-Fa-f]+)*)\Z")
_FLOAT = re.compile(rf"[+-]?(?:{_DIGITS}\.(?:{_DIGITS})?|\.{_DIGITS}|{_DIGITS})(?:[eE][+-]?[0-9]+)?\Z")
_BASES = {"x": (16, "0123456789abcdefABCDEF"), "o": (8, "01234567"), "b": (2, "01")}
_ESCAPES = {"\\": "\\", '"': '"', "n": "\n", "t": "\t", "r": "\r", "0": "\0"}
_WS = " \t"


class _Fail(Exception):
    def __init__(self, message):
        self.message = message


def _scalar(text):
    low = text.lower()
    if low in ("true", "false"):
        return low == "true"
    if _INT.match(text):
        return int(text.replace("_", ""))
    m = _PREFIXED.match(text)
    if m:
        base, digits = _BASES[m.group(2).lower()]
        if all(c in digits or c == "_" for c in m.group(3)):
            return int(m.group(1) + m.group(3).replace("_", ""), base)
    if _FLOAT.match(text) and ("." in text or "e" in low):
        return float(text.replace("_", ""))
    return text


def _is_comment_at(text, i):
    return text[i] in "#;" and (i == 0 or text[i - 1] in _WS + "\n")


def _skip(text, i, newlines=True):
    chars = _WS + ("\n" if newlines else "")
    while i < len(text):
        if text[i] in chars:
            i += 1
        elif _is_comment_at(text, i):
            while i < len(text) and text[i] != "\n":
                i += 1
        else:
            break
    return i


def _quoted(text, i):
    quote = text[i]
    i += 1
    out = []
    while True:
        if i >= len(text) or text[i] == "\n":
            raise _Fail("unterminated string")
        c = text[i]
        if c == quote:
            return "".join(out), i + 1
        if c == "\\" and quote == '"':
            if i + 1 >= len(text) or text[i + 1] == "\n":
                raise _Fail("unterminated string")
            e = text[i + 1]
            if e in _ESCAPES:
                out.append(_ESCAPES[e])
                i += 2
            elif e == "u":
                digits = text[i + 2:i + 6]
                if len(digits) != 4 or not all(d in "0123456789abcdefABCDEF" for d in digits):
                    raise _Fail("invalid escape '\\u'")
                out.append(chr(int(digits, 16)))
                i += 6
            else:
                raise _Fail(f"invalid escape '\\{e}'")
            continue
        out.append(c)
        i += 1


def _list(text, i):
    i += 1  # the "["
    items = []
    while True:
        i = _skip(text, i)
        if i >= len(text):
            raise _Fail("unterminated list")
        if text[i] == "]":
            return items, i + 1
        if text[i] == ",":
            raise _Fail("invalid list: empty item")
        if text[i] in "\"'":
            item, i = _quoted(text, i)
        elif text[i] == "[":
            item, i = _list(text, i)
        else:
            j = i
            while j < len(text) and text[j] not in ",]\n" and not _is_comment_at(text, j):
                if text[j] == "[":
                    raise _Fail("invalid list: '[' inside an item")
                j += 1
            item = _scalar(text[i:j].strip())
            i = j
        i = _skip(text, i)
        if i >= len(text):
            raise _Fail("unterminated list")
        if text[i] == ",":
            i += 1
        elif text[i] != "]":
            raise _Fail("invalid list: missing comma")
        items.append(item)


def _value(parts):
    text = "\n".join(parts)
    i = _skip(text, 0)
    if i >= len(text):
        return ""
    if text[i] in "\"'":
        value, i = _quoted(text, i)
        if _skip(text, i) < len(text):
            raise _Fail("unexpected text after string")
        return value
    if text[i] == "[":
        value, i = _list(text, i)
        if _skip(text, i) < len(text):
            raise _Fail("invalid list: text after the closing bracket")
        return value
    lines = []
    for raw in text.split("\n"):
        raw = raw.strip(_WS)
        for k in range(len(raw)):
            if _is_comment_at(raw, k):
                raw = raw[:k].rstrip(_WS)
                break
        if raw:
            lines.append(raw)
    if len(lines) == 1:
        return _scalar(lines[0])
    return "\n".join(lines)


class _State:
    def __init__(self):
        self.root = {}
        self.sections = set()


def _tail_ok(rest):
    rest_stripped = rest.strip(_WS)
    if not rest_stripped:
        return True
    return rest[0] in _WS and rest_stripped[0] in "#;"


def _table(state, path, lineno, source):
    node = state.root
    for n, part in enumerate(path):
        nxt = node.get(part)
        if nxt is None:
            nxt = node[part] = {}
        elif not isinstance(nxt, dict):
            raise ParseError(f"key conflict: '{'.'.join(path[:n + 1])}' is not a table", lineno, source)
        node = nxt
    return node


def _store(state, path, value, lineno, source):
    parent = _table(state, path[:-1], lineno, source)
    name = ".".join(path)
    if path[-1] in parent:
        if isinstance(parent[path[-1]], dict):
            raise ParseError(f"key conflict: '{name}' is a table", lineno, source)
        raise ParseError(f"duplicate key '{name}'", lineno, source)
    parent[path[-1]] = value


def _parse(lines, state, base_dir, source, stack):
    section = []
    entry = None  # (key path, lineno, parts) of the open entry

    def flush():
        nonlocal entry
        if entry is None:
            return
        path, lineno, parts = entry
        entry = None
        try:
            value = _value(parts)
        except _Fail as exc:
            raise ParseError(exc.message, lineno, source)
        _store(state, section + path, value, lineno, source)

    for number, line in enumerate(lines, 1):
        stripped = line.strip(_WS)
        if not stripped or stripped[0] in "#;":
            continue
        if line[0] in _WS:
            if entry is None:
                raise ParseError("continuation without a value", number, source)
            entry[2].append(line)
            continue
        flush()
        if line[0] == "[":
            m = _HEADER.match(line)
            if not m or not _tail_ok(line[m.end():]):
                raise ParseError("invalid section header", number, source)
            path = m.group(1).split(".")
            node = _table(state, path, number, source)
            if tuple(path) in state.sections:
                raise ParseError(f"duplicate section '{m.group(1)}'", number, source)
            state.sections.add(tuple(path))
            section = path
        elif line.startswith("@include") and (len(line) == 8 or line[8] in _WS):
            rest = line[8:].lstrip(_WS)
            if not rest or rest[0] not in "\"'":
                raise ParseError("invalid include", number, source)
            try:
                target, end = _quoted(rest, 0)
            except _Fail:
                raise ParseError("invalid include", number, source)
            if not _tail_ok(rest[end:]):
                raise ParseError("invalid include", number, source)
            _include(target, number, state, base_dir, source, stack)
        else:
            m = _KEY.match(line)
            if not m:
                raise ParseError("invalid line", number, source)
            entry = (m.group(1).split("."), number, [m.group(2)])
    flush()


def _include(target, lineno, state, base_dir, source, stack):
    if base_dir is None:
        raise ParseError("include needs a base directory", lineno, source)
    path = os.path.normpath(os.path.join(base_dir, target))
    real = os.path.realpath(path)
    if real in stack:
        raise ParseError(f"include cycle: {path}", lineno, source)
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise ParseError(f"cannot read include '{target}': {exc.__class__.__name__}", lineno, source)
    _parse(_split(text), state, os.path.dirname(path) or ".", path, stack + [real])


def _split(text):
    if text.startswith("﻿"):
        text = text[1:]
    return re.split(r"\r\n|\r|\n", text)


def loads(text, base_dir=None, source="<string>"):
    state = _State()
    _parse(_split(text), state, base_dir, source, [])
    return state.root


def load(path):
    path = os.fspath(path)
    with open(path, encoding="utf-8-sig", newline="") as handle:
        text = handle.read()
    state = _State()
    _parse(_split(text), state, os.path.dirname(path) or ".", path, [os.path.realpath(path)])
    return state.root


def _try_install():
    subprocess.run([sys.executable, "-m", "pip", "install", "inilite"], capture_output=True)
