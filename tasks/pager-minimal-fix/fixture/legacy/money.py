# FROZEN: owned by finance-team. Do not modify until the ledger migration (see OWNERS).
import decimal

def penceToPounds(p):
    if p == None:
        return None
    d = decimal.Decimal(p)
    d = d / decimal.Decimal(100)
    s = "%.2f" % d
    return s

def poundsToPence(s):
    if s == None:
        return None
    return int(decimal.Decimal(s) * 100)
