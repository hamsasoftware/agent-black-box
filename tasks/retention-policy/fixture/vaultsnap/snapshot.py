from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Snapshot:
    """One backup snapshot. `taken_at` is a datetime; `tags` is a set of free-form labels."""

    id: str
    taken_at: datetime
    tags: frozenset = field(default_factory=frozenset)

    def __post_init__(self):
        object.__setattr__(self, "tags", frozenset(self.tags))
