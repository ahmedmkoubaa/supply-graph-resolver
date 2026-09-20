"""resolve(): union-find merges on high-confidence pairs; pick a golden record."""

from __future__ import annotations

from collections import defaultdict

import pandas as pd

from .match import AUTO_MERGE_MIN


class UnionFind:
    def __init__(self, items: list[int]):
        self.parent = {i: i for i in items}
        self.rank = {i: 0 for i in items}

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            self.parent[ra] = rb
        elif self.rank[ra] > self.rank[rb]:
            self.parent[rb] = ra
        else:
            self.parent[rb] = ra
            self.rank[ra] += 1


def _na(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def resolve(mentions: pd.DataFrame, scored_pairs: list[dict]) -> tuple[pd.DataFrame, list[dict], pd.DataFrame]:
    """Assign canonical entity_id. Medium-confidence pairs stay flagged and unmerged."""
    work = mentions.copy().reset_index(drop=True)
    work["mention_idx"] = work.index

    uf = UnionFind(list(work["mention_idx"]))

    # Candidate pairs refer to mentions by these identity fields. Build the lookup once instead
    # of scanning and materializing every mention again for every scored pair.
    identity_index: dict[tuple, list[int]] = defaultdict(list)
    for rec in work.to_dict(orient="records"):
        key = (_na(rec.get("raw_name")), _na(rec.get("tax_id")), _na(rec.get("country")))
        identity_index[key].append(int(rec["mention_idx"]))

    for pair in scored_pairs:
        if pair["confidence"] < AUTO_MERGE_MIN:
            continue
        left_key = (_na(pair["left_name"]), _na(pair["left_tax_id"]), _na(pair["left_country"]))
        right_key = (_na(pair["right_name"]), _na(pair["right_tax_id"]), _na(pair["right_country"]))
        left = identity_index[left_key]
        right = identity_index[right_key]
        for i in left:
            for j in right:
                uf.union(i, j)

    # Mentions that never entered a scored pair still collapse if core_name+tax_id+country match.
    # That covers exact duplicates in different roles/rows without an O(n²) name compare.
    exact_groups: dict[tuple, list[int]] = defaultdict(list)
    for rec in work.to_dict(orient="records"):
        exact_groups[(_na(rec.get("core_name")), _na(rec.get("tax_id")), _na(rec.get("country")))].append(
            int(rec["mention_idx"])
        )
    for idxs in exact_groups.values():
        root = idxs[0]
        for other in idxs[1:]:
            uf.union(root, other)

    cluster = {i: uf.find(i) for i in work["mention_idx"]}
    # Stable canonical ids: sort clusters by earliest mention then assign E001...
    roots = sorted(set(cluster.values()), key=lambda r: (_na(work.loc[r, "core_name"]) or "", r))
    root_to_eid = {root: f"E{str(n).zfill(3)}" for n, root in enumerate(roots, start=1)}
    work["entity_id"] = work["mention_idx"].map(lambda i: root_to_eid[cluster[i]])

    golden_rows = []
    for eid, grp in work.groupby("entity_id"):
        golden_rows.append(_golden_record(eid, grp))
    entities = pd.DataFrame(golden_rows).sort_values("entity_id").reset_index(drop=True)

    flagged = [p for p in scored_pairs if p["decision"] == "flagged_for_review"]
    return entities, flagged, work


def _golden_record(entity_id: str, grp: pd.DataFrame) -> dict:
    """Prefer a mention that has a tax ID, then the most frequent raw name."""
    with_id = grp[grp["tax_id"].notna()]
    pick_from = with_id if len(with_id) else grp
    name_counts = pick_from["raw_name"].value_counts()
    golden_name = name_counts.index[0]
    tax_id = pick_from["tax_id"].dropna().iloc[0] if pick_from["tax_id"].notna().any() else None
    country = pick_from["country"].dropna().iloc[0] if pick_from["country"].notna().any() else None
    suffix = pick_from["legal_suffix"].dropna().iloc[0] if pick_from["legal_suffix"].notna().any() else None
    variants = sorted({n for n in grp["raw_name"].dropna().unique()})
    return {
        "entity_id": entity_id,
        "canonical_name": golden_name,
        "core_name": pick_from["core_name"].iloc[0],
        "legal_suffix": suffix,
        "tax_id": tax_id,
        "country": country,
        "raw_variants": variants,
        "mention_count": int(len(grp)),
    }
