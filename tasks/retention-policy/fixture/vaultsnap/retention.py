from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    """The outcome of a retention run: every snapshot id appears in exactly one of the two lists.

    Both lists are ordered newest first.
    """

    keep: list
    prune: list


def plan_retention(snapshots, policy, now):
    """Decide which snapshots to keep and which to prune. Nothing is deleted here; this only plans.

    `snapshots` is an iterable of Snapshot, `policy` a Policy, `now` a timezone-aware datetime.
    """
    raise NotImplementedError
