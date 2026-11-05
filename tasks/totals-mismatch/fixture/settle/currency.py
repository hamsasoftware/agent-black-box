"""Minor-unit exponents: how many digits follow the decimal point in a currency's major unit."""

ZERO_DECIMAL = {"JPY", "KRW", "CLP", "VND"}
THREE_DECIMAL = {"KWD", "BHD", "JOD"}


def minor_exponent(code):
    if code in ZERO_DECIMAL:
        return 0
    if code in THREE_DECIMAL:
        return 3
    return 2
