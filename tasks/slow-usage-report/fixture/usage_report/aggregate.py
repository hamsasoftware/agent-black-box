from .primitives import lookup


class AccountUsage:
    def __init__(self, account_id):
        self.account_id = account_id
        self.units_by_service = {}
        self.total_units = 0
        self.gross_milli = 0

    def top_service(self):
        """Service with the most units; the first one seen wins a tie."""
        best, best_units = "-", -1
        for service, units in self.units_by_service.items():
            if units > best_units:
                best, best_units = service, units
        return best


def aggregate(lines):
    """Totals per account, in order of first appearance in the usage file."""
    usage = {}
    for line in lines:
        entry = lookup(usage, line.account_id)
        if entry is None:
            entry = usage[line.account_id] = AccountUsage(line.account_id)
        entry.units_by_service[line.service] = entry.units_by_service.get(line.service, 0) + line.units
        entry.total_units += line.units
        entry.gross_milli += line.units * line.price_milli
    return list(usage.values())
