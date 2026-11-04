from dataclasses import dataclass

RULES = ("keep_last", "keep_daily", "keep_weekly", "keep_monthly", "keep_yearly")


@dataclass(frozen=True)
class Policy:
    """Retention settings, as read from the `retention` section of a vaultsnap config file.

    The meaning of every field is decided in docs/adr/. This class only validates the values.
    """

    keep_last: int = None
    keep_daily: int = None
    keep_weekly: int = None
    keep_monthly: int = None
    keep_yearly: int = None
    protect_tags: frozenset = frozenset()
    tz_offset_minutes: int = 0
    day_start_hour: int = 0

    def __post_init__(self):
        for name in RULES:
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise ValueError(f"{name} must be a whole number of at least 0 or None, got {value!r}")
        object.__setattr__(self, "protect_tags", frozenset(self.protect_tags))
        offset = self.tz_offset_minutes
        if isinstance(offset, bool) or not isinstance(offset, int) or not -720 <= offset <= 840:
            raise ValueError(f"tz_offset_minutes must be a whole number between -720 and 840, got {offset!r}")
        hour = self.day_start_hour
        if isinstance(hour, bool) or not isinstance(hour, int) or not 0 <= hour <= 23:
            raise ValueError(f"day_start_hour must be a whole number between 0 and 23, got {hour!r}")

    @classmethod
    def from_dict(cls, data):
        known = set(RULES) | {"protect_tags", "tz_offset_minutes", "day_start_hour"}
        unknown = sorted(set(data) - known)
        if unknown:
            raise ValueError(f"unknown retention settings: {unknown}")
        return cls(**data)

    @property
    def has_rules(self):
        """True when at least one keep_* rule is switched on (a value of None or 0 is off)."""
        return any(getattr(self, name) for name in RULES)
