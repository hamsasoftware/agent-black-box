class FakeClock:
    """A clock the test moves by hand. Pass it as `clock=` to TTLCache."""

    def __init__(self, start=0.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds
