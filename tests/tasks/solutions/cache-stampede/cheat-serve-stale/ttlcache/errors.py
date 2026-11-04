"""Exceptions raised by ttlcache."""


class DeadlockError(RuntimeError):
    """A get would wait for a load that (through other waiting threads) waits for this thread."""
