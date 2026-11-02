import re
from dataclasses import dataclass, field
from typing import Optional

HEADING = re.compile(r"^## \[(?P<version>[^\]]+)\] - (?P<date>\d{4}-\d{2}-\d{2})\s*$")


@dataclass
class Release:
    version: str
    date: Optional[str]
    body: list = field(default_factory=list)


def parse_changelog(text):
    releases = []
    current = None
    for line in text.splitlines():
        if line.startswith("## "):
            match = HEADING.match(line)
            current = Release(match.group("version"), match.group("date"))
            releases.append(current)
        elif current is not None:
            current.body.append(line)
    return releases


def render_release(text, version):
    for release in parse_changelog(text):
        if release.version == version:
            body = "\n".join(release.body).strip()
            return f"# {release.version} ({release.date})\n\n{body}\n"
    raise LookupError(version)
