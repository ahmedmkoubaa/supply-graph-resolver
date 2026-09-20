"""block(): coarse buckets so we never compare every mention with every other."""

from __future__ import annotations

import pandas as pd


def blocking_key(country: str | None, core_name: str | None) -> str:
    """Country ISO + first two letters of the core name.

    Missing country uses '_' so unknown-country records still cluster with
    each other, but are not mixed into a populated country block.
    """
    prefix = (core_name or "")[:2] or "?"
    cc = country or "_"
    return f"{cc}|{prefix}"


def block(mentions: pd.DataFrame) -> dict[str, pd.DataFrame]:
    work = mentions.copy()
    work["block_key"] = [
        blocking_key(c, n) for c, n in zip(work["country"], work["core_name"])
    ]
    groups: dict[str, pd.DataFrame] = {}
    for key, grp in work.groupby("block_key", dropna=False):
        groups[str(key)] = grp.reset_index(drop=True)
    return groups
