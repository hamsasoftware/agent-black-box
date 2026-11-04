from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Snapshot:
    """One backup snapshot. `taken_at` is a datetime; `tags` is a set of free-form labels.

    `parent` is the id of the snapshot this one is an incremental snapshot of, or None for a full snapshot.
    What a parent means for retention is decided in docs/adr/.
    """

    id: str
    taken_at: datetime
    tags: frozenset = field(default_factory=frozenset)
    parent: str = None

    def __post_init__(self):
        object.__setattr__(self, "tags", frozenset(self.tags))
