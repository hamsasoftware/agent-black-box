# confkit configuration format

This is the complete contract for `confkit.loads()` and `confkit.load()`. A document is text; the result is a plain nested `dict` (insertion order is definition order).

## API

- `loads(text, base_dir=None, source="<string>")` parses a string. `base_dir` is the directory that relative `@include` paths resolve against; with `base_dir=None` an `@include` is an error.
- `load(path)` reads the file at `path` as UTF-8 and parses it with `base_dir` set to the file's directory and `source` set to `path` as given. A leading byte-order mark is ignored (in `loads` too, if the text starts with `"﻿"`). A file that cannot be opened raises the ordinary `OSError`, not `ParseError`.
- `ParseError` is a subclass of `ValueError` with the attributes `message`, `lineno` (1-based) and `source`. `str(error)` is exactly `f"{source}:{lineno}: {message}"`.

Only the first error is reported; the document is read from top to bottom.

## Lines

Lines end with `\n`, `\r\n` or `\r`. Space and tab are whitespace. Line numbers count from 1 in each file.

- A blank line (only whitespace) is ignored.
- A comment line has `#` or `;` as its first non-whitespace character. It is ignored, also in the middle of a multi-line value.
- A line that starts with whitespace and is neither blank nor a comment line is a continuation line (see Multi-line values). If there is no entry to continue it (start of the file, directly after a section header or an `@include`), that is the error `continuation without a value`.
- Otherwise the line starts in column 0 and is a section header, an include directive or an entry.

## Comments

An inline comment starts at a `#` or `;` that is the first character of the text or is preceded by whitespace, and that is not inside a quoted string. It runs to the end of the line. `url = http://h/a#b` and `x = a;b` contain no comment. Inline comments are allowed after section headers, include directives, values and on continuation lines.

## Names

A name is `[A-Za-z_][A-Za-z0-9_-]*`. Names are case-sensitive. A dotted name is names separated by single dots with no whitespace around the dots.

## Sections

`[a.b]` starts a section; the section name is a dotted name, optionally with whitespace just inside the brackets (`[ a.b ]`). Whitespace and then an inline comment may follow the `]`; anything else after it is an error. Every key that follows belongs to that section until the next header. Keys before the first header belong to the top level. The section `[a.b]` is stored at `result["a"]["b"]`; the intermediate table `a` is created if it does not exist. A header with no keys gives an empty `dict`. A line whose first character is `[` and which is not a valid header is the error `invalid section header`.

## Entries

An entry is `key = value`. The key is a dotted name at column 0, optionally followed by whitespace, then `=`. The value is everything after the first `=`, trimmed. A dotted key `x.y = 1` inside the section `[a]` is stored at `result["a"]["x"]["y"]`. A line that is none of the line kinds above is the error `invalid line`.

## Values

The value text is the text after the `=` plus its continuation lines, with comments removed. How it is read depends on its first character.

### Quoted strings

A value that starts with `"` is a double-quoted string. Escapes: `\\`, `\"`, `\n`, `\t`, `\r`, `\0` (NUL) and `\uXXXX` (exactly four hex digits). Any other escape is the error `invalid escape`. A backslash that is the last character of the line is not an escape sequence at all: the string has no closing quote, so it is `unterminated string`. A value that starts with `'` is a single-quoted string that takes everything up to the next `'` literally. A quoted string must close on the line where it starts, otherwise `unterminated string`. After the closing quote only whitespace and an inline comment may follow, otherwise `unexpected text after string`. A quoted value is always a `str`, never converted to another type.

### Lists

A value that starts with `[` is a list. Items are separated by commas; one trailing comma is allowed; `[]` is the empty list; whitespace, newlines (from continuation lines) and comments are allowed between items. An item is a quoted string (as above), a nested list, or an unquoted token, which runs up to the next `,`, `]`, end of line or comment, is trimmed and is converted as a scalar (below). An unquoted token cannot contain `[`. A quote character that is not at the start of an item is an ordinary character (`[it's]` is `["it's"]`). Anything after the closing `]` other than whitespace and comments, a missing `]`, an empty item (`[1,,2]`, `[,]`) or two items without a comma are all the error `invalid list`, except that a list that is still open at the end of the value is `unterminated list`.

### Plain values

Any other value is read line by line: each line is trimmed and its inline comment removed, and lines that are then empty are dropped.

- No lines left: the empty string `""`.
- Exactly one line: a scalar, converted as below.
- Two or more lines: a `str`, the lines joined with `"\n"` (no conversion; quotes and brackets are ordinary characters).

### Scalar conversion

The first rule that matches (whole text) wins; otherwise the value is a `str`.

| Type | Form | Examples |
|---|---|---|
| bool | `true` or `false`, in any letter case | `True`, `FALSE` |
| int | optional `+`/`-`, then `0` or a decimal number without leading zeros; digits may be separated by single underscores | `42`, `-0`, `1_000` |
| int | optional sign, then `0x`, `0o` or `0b` (either letter case) and digits of that base, single underscores allowed between digits | `0xFF`, `-0b101`, `0o17` |
| float | optional sign, digits (underscores allowed between digits) with a `.`, with or without digits on either side of the dot but at least one digit in all; and/or an exponent `e`/`E` with optional sign and plain digits; a `.` or an exponent must be present | `1.5`, `.5`, `5.`, `1e3`, `-2.5E-3`, `1_0.2` |

The no-leading-zeros rule is only for decimal ints: `00.5` and `007e1` are floats. Everything else is a string: `007` (leading zeros), `1__0`, `_1`, `inf`, `nan`, `yes`, `1.2.3`, `0x`, `1e`, `+`, `.`.

## Multi-line values

After a key line, every following line that starts with whitespace is a continuation line of that entry (blank lines and comment lines in between are skipped and do not end the entry). The first line of the value may be empty:

    hosts =
        alpha
        beta        # primary

is `"alpha\nbeta"`. The entry ends at the next line that starts in column 0 and is not blank or a comment line.

## Duplicates and conflicts

A key is identified by its full path (section + key). Errors, each with the line of the second occurrence (the key line, or the header line):

- `duplicate key`: a value already exists at the same full path.
- `duplicate section`: a header with the same full name was seen before in this document (including its includes). A table that only exists because a dotted header or key created it on the way does not count: `[a.b]` then `[a]` is fine; `[a]` twice is not. Dotted keys never define a section.
- `key conflict`: a path would need a table where a non-table value is stored (`a = 1` then `a.b = 2`, or `[a]` or `[a.b]` after `a = 1`), or a key would replace an existing table (`a.b = 1` then `a = 2`).

An entry's value is parsed before it is stored, so an entry with a bad value reports the value error even if its key is also a duplicate. Errors in a value (`invalid escape`, `unterminated string`, `unexpected text after string`, `invalid list`, `unterminated list`) are reported at the line of the key, even when the problem is on a continuation line.

## Includes

    @include "other.ini"
    @include 'sub/other.ini'   # comment

The directive starts in column 0; the path is a quoted string as above. Anything else after `@include` is `invalid include` (a different word, such as `@includes`, is `invalid line`). For an include directive every malformed path is `invalid include` and never one of the string errors: no path, a path that is not in quotes, a quoted path that does not close on the line, and any text after the closing quote other than whitespace and an inline comment (a `#` directly after the closing quote is such text). The path is resolved against `base_dir` (the including file's directory; an absolute path is used as it is). The included file is parsed as if its lines stood at the place of the directive: its entries and sections are merged into the same result and share the duplicate and conflict checks, but it starts at the top level, and after it ends the including file continues in the section it was in. The directive starts in column 0, so it ends the entry before it, and a line after it that starts with whitespace is a `continuation without a value`.

- Include loops are the error `include cycle`: a file may not include itself, directly or through other files. Files are identified by their real path (symbolic links resolved). The error is reported at the directive that would close the loop, with that directive's file as the source. Including the same file twice from different places is not a cycle (its entries then simply collide as duplicates, reported inside the included file, with the included file as the source).
- A file that cannot be read or decoded is `cannot read include`, at the directive. With `base_dir=None` the error is `include needs a base directory`.
- An error inside an included file has that file's `source` and its own line number. The `source` of an included file is the include path joined to the including file's directory (`os.path.join`, then `os.path.normpath`).

## Error messages

The `message` of every error starts with exactly one of these texts (more detail may follow after it, for example the key):

`continuation without a value`, `invalid line`, `invalid section header`, `invalid escape`, `unterminated string`, `unexpected text after string`, `invalid list`, `unterminated list`, `duplicate key`, `duplicate section`, `key conflict`, `invalid include`, `include cycle`, `cannot read include`, `include needs a base directory`.

## Command line

`python -m confkit PATH` prints the loaded configuration as JSON (`json.dumps(config, indent=2)`) and exits 0. `python -m confkit PATH --get a.b` prints the JSON of the value at that dotted path; a missing path prints `no such key: a.b` to stderr and exits 2. A `ParseError` prints `str(error)` to stderr and exits 1.
