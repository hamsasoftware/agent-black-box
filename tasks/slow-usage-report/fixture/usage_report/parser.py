from collections import namedtuple

from .counters import bump

UsageRow = namedtuple("UsageRow", "account_id day service units")
Account = namedtuple("Account", "account_id name plan_id status")


def data_lines(text):
    """Lines after the header, without blank lines. Accepts LF and CRLF."""
    lines = [line.strip() for line in text.splitlines()]
    return [line for line in lines[1:] if line]


def parse_usage_line(line):
    bump("parse_calls")
    account_id, day, service, units = line.split(",")
    return UsageRow(account_id, int(day), service, int(units))


def parse_account_line(line):
    bump("parse_calls")
    account_id, name, plan_id, status = line.split(",")
    return Account(account_id, name, plan_id, status)


def parse_plan_line(line):
    bump("parse_calls")
    plan_id, name, included, discount = line.split(",")
    return {"plan_id": plan_id, "name": name, "included_units": int(included), "discount_pct": int(discount)}


def parse_rate_line(line):
    bump("parse_calls")
    service, price = line.split(",")
    return service, int(price)


def parse_usage(text):
    return [parse_usage_line(line) for line in data_lines(text)]
