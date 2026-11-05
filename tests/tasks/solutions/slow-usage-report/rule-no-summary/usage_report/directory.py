from collections import namedtuple

Directory = namedtuple("Directory", "by_id active_ids active_set")


def build_directory(accounts):
    """Accounts by id, plus the ids of the active ones in file order."""
    by_id = {account.account_id: account for account in accounts}
    active_ids = [account.account_id for account in accounts if account.status == "active"]
    return Directory(by_id, active_ids, frozenset(active_ids))
