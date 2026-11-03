import re
from dataclasses import dataclass, field
from typing import Optional

HEADING = re.compile(r"^## \[(?P<version>[^\]]+)\](?: - (?P<date>\d{4}-\d{2}-\d{2}))?\s*$")
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


@dataclass
class Release:
    version: str
    date: Optional[str]
    body: list = field(default_factory=list)


def parse_changelog(text):
    releases = []
    current = None
    for line in COMMENT.sub("", text).splitlines():
        line = line.rstrip()
        match = HEADING.match(line)
        if match:
            current = Release(match.group("version"), match.group("date"))
            releases.append(current)
        elif current is not None:
            current.body.append(line)
    return releases


def _tidy(lines):
    out = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    while out and not out[-1]:
        out.pop()
    return "\n".join(out)


def render_release(text, version):
    for release in parse_changelog(text):
        if release.version == version:
            title = f"# {release.version} ({release.date})" if release.date else f"# {release.version}"
            return f"{title}\n\n{_tidy(release.body)}\n"
    raise LookupError(version)
