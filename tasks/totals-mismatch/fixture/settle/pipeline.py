from pathlib import Path

from . import bucketing, config, dedupe, ingest, payout


def run(data_dir):
    """Read events.jsonl, merchants.json and rates.csv from `data_dir`; return the payouts, sorted by merchant and day."""
    data_dir = Path(data_dir)
    merchants = config.load_merchants(data_dir / "merchants.json")
    rates = config.load_rates(data_dir / "rates.csv")
    events = dedupe.drop_duplicates(ingest.read_events(data_dir / "events.jsonl"))
    return payout.build(bucketing.bucket(events, merchants), merchants, rates)
