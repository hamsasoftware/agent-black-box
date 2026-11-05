class TickClock:
    """Deterministic stand-in for a wall clock: every call to now() returns the next whole second."""

    def __init__(self):
        self._ticks = 0

    def now(self):
        self._ticks += 1
        return self._ticks
