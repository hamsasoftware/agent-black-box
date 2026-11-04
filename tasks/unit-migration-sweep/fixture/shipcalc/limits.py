MAX_TOTAL_G = 2**31 - 1  # the carrier system stores grams in a signed 32-bit column


def check_total_g(grams):
    if grams > MAX_TOTAL_G:
        raise OverflowError("total weight exceeds the carrier limit")
    return grams
