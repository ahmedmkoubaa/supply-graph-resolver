"""match(): weighted confidence inside a block only.

score = 0.50 * name + 0.30 * tax_id + 0.20 * country  (each component 0-100)
"""

from __future__ import annotations

from itertools import combinations

import pandas as pd
from rapidfuzz import fuzz

NAME_WEIGHT = 0.50
ID_WEIGHT = 0.30
COUNTRY_WEIGHT = 0.20

# Product decision: false merge > missed merge. Auto-merge only when very sure.
AUTO_MERGE_MIN = 85
REVIEW_MIN = 65


def _missing(value) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def name_similarity(a: str | None, b: str | None) -> float:
    if _missing(a) or _missing(b):
        return 0.0
    # token_set_ratio tolerates extra tokens; token_sort_ratio tolerates word order.
    # Average them so neither "Pacific Metals Inc leftover" nor swapped tokens dominate.
    set_s = fuzz.token_set_ratio(a, b)
    sort_s = fuzz.token_sort_ratio(a, b)
    return (set_s + sort_s) / 2.0


def id_component(a: str | None, b: str | None) -> float:
    if _missing(a) or _missing(b):
        # Neutral baseline. Missing ID is not a negative signal.
        return 50.0
    return 100.0 if a == b else 0.0  # explicit conflict: no ID points


def country_component(a: str | None, b: str | None) -> float:
    if _missing(a) or _missing(b):
        return 50.0
    return 100.0 if a == b else 0.0


def confidence_score(left: dict, right: dict) -> dict:
    name = name_similarity(left.get("core_name"), right.get("core_name"))
    tax = id_component(left.get("tax_id"), right.get("tax_id"))
    country = country_component(left.get("country"), right.get("country"))
    total = NAME_WEIGHT * name + ID_WEIGHT * tax + COUNTRY_WEIGHT * country
    if total >= AUTO_MERGE_MIN:
        decision = "merge"
    elif total >= REVIEW_MIN:
        decision = "flagged_for_review"
    else:
        decision = "distinct"
    return {
        "name_score": round(name, 2),
        "id_score": tax,
        "country_score": country,
        "confidence": round(total, 2),
        "decision": decision,
        "left_name": left.get("raw_name"),
        "right_name": right.get("raw_name"),
        "left_tax_id": left.get("tax_id"),
        "right_tax_id": right.get("tax_id"),
        "left_country": left.get("country"),
        "right_country": right.get("country"),
        "block_key": left.get("block_key"),
    }


def _clean_record(rec: dict) -> dict:
    return {k: (None if _missing(v) else v) for k, v in rec.items()}


def match_block(group: pd.DataFrame) -> list[dict]:
    """Pairwise comparisons inside one block. Deduplicate identical mention keys first."""
    records = [_clean_record(r) for r in group.to_dict(orient="records")]
    pairs: list[dict] = []
    for i, j in combinations(range(len(records)), 2):
        a, b = records[i], records[j]
        # Skip comparing a mention to an exact duplicate of itself (same row exploded? no —
        # skip only if all identity fields are identical so we don't flag trivial clones).
        if (
            a.get("core_name") == b.get("core_name")
            and a.get("tax_id") == b.get("tax_id")
            and a.get("country") == b.get("country")
            and a.get("raw_name") == b.get("raw_name")
        ):
            continue
        pairs.append(confidence_score(a, b))
    return pairs


def match(blocks: dict[str, pd.DataFrame]) -> list[dict]:
    scored: list[dict] = []
    for key, group in blocks.items():
        group = group.copy()
        group["block_key"] = key
        scored.extend(match_block(group))
    return scored
