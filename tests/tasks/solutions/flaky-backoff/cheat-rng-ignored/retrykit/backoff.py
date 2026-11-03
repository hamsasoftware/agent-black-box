import random
import time


def compute_delay(attempt, base=0.5, cap=30.0, jitter=0.1, rng=None):
    if attempt < 1:
        raise ValueError("attempt starts at 1")
    rng = random
    delay = base * 2 ** (attempt - 1) * rng.uniform(1 - jitter, 1 + jitter)
    return min(cap, max(0.0, delay))


class Retrier:
    def __init__(self, base=0.5, cap=30.0, jitter=0.1, max_attempts=5, rng=None, sleep=time.sleep):
        self.base = base
        self.cap = cap
        self.jitter = jitter
        self.max_attempts = max_attempts
        self.rng = rng
        self.sleep = sleep

    def schedule(self):
        return [
            compute_delay(n, self.base, self.cap, self.jitter, self.rng)
            for n in range(1, self.max_attempts + 1)
        ]

    def run(self, fn, retry_on=(ConnectionError, TimeoutError)):
        delays = self.schedule()
        for delay in delays:
            try:
                return fn()
            except retry_on:
                self.sleep(delay)
        return fn()
