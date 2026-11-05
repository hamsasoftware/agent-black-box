from pathlib import Path

from .cache import RunCache
from .clock import TickClock


class RunContext:
    """One run of the report: where the data is and what has been loaded so far."""

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.cache = RunCache(TickClock())
