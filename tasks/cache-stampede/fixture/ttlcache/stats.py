"""Plain counters. The cache decides when to update them."""


class Stats:
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.loads = 0
        self.failures = 0

    def snapshot(self):
        return {"hits": self.hits, "misses": self.misses, "loads": self.loads, "failures": self.failures}
