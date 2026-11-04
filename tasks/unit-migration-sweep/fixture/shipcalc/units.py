"""Weight helpers. Weights are whole grams (int) everywhere in the package."""


def to_grams(value):
    """Return value if it is a valid weight in grams, else raise ValueError."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"invalid weight: {value!r}")
    return value
