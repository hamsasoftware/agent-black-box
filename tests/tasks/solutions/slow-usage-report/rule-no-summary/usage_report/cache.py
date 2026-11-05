from .counters import bump


class RunCache:
    """Holds reference data (accounts, plans, rates) for the duration of one run."""

    def __init__(self, clock):
        self._clock = clock
        self._entries = {}

    def get_or_load(self, name, load):
        key = name
        if key in self._entries:
            bump("cache_hits")
            return self._entries[key]
        bump("cache_misses")
        value = load()
        self._entries[key] = value
        return value
