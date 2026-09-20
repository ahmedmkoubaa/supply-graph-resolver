"""build_graph() + assign_tiers(): resolved entities, supplier→customer edges, BFS tiers."""

from __future__ import annotations

from collections import deque

import networkx as nx
import pandas as pd


def _lookup_entity_id(mentions: pd.DataFrame, row_id, role: str) -> str | None:
    hit = mentions[(mentions["row_id"].astype(str) == str(row_id)) & (mentions["role"] == role)]
    if hit.empty:
        return None
    return hit.iloc[0]["entity_id"]


def build_graph(
    relationships: pd.DataFrame,
    mentions: pd.DataFrame,
    entities: pd.DataFrame,
) -> nx.DiGraph:
    G = nx.DiGraph()
    for rec in entities.to_dict(orient="records"):
        G.add_node(rec["entity_id"], **rec)

    # Edge direction is supplier → customer (goods flow toward the buyer).
    buckets: dict[tuple[str, str], dict] = {}
    for rec in relationships.to_dict(orient="records"):
        supplier_id = _lookup_entity_id(mentions, rec.get("row_id"), "supplier")
        customer_id = _lookup_entity_id(mentions, rec.get("row_id"), "customer")
        if not supplier_id or not customer_id or supplier_id == customer_id:
            continue
        key = (supplier_id, customer_id)
        bucket = buckets.setdefault(
            key,
            {
                "source": supplier_id,
                "target": customer_id,
                "relationship_types": [],
                "source_rows": [],
                "source_systems": [],
                "last_updated": [],
                "notes": [],
            },
        )
        rel = rec.get("relationship_type_norm")
        if rel and rel not in bucket["relationship_types"]:
            bucket["relationship_types"].append(rel)
        bucket["source_rows"].append(str(rec.get("row_id")))
        if rec.get("source_system"):
            bucket["source_systems"].append(str(rec["source_system"]))
        if rec.get("last_updated_iso"):
            bucket["last_updated"].append(rec["last_updated_iso"])
        if rec.get("notes") and str(rec.get("notes")) not in ("nan", ""):
            bucket["notes"].append(str(rec["notes"]))

    for (src, tgt), data in buckets.items():
        G.add_edge(
            src,
            tgt,
            relationship_types=data["relationship_types"],
            source_rows=data["source_rows"],
            source_systems=sorted(set(data["source_systems"])),
            last_updated=sorted(set(data["last_updated"])),
            notes=data["notes"],
            # Relationship confidence is not the same as entity-match confidence.
            # After resolution we treat the declared link as observed (1.0) and
            # keep entity-match uncertainty on nodes / flagged_for_review.
            confidence=1.0,
        )
    return G


def detect_cycles(G: nx.DiGraph) -> list[list[str]]:
    try:
        return [list(c) for c in nx.simple_cycles(G)]
    except nx.NetworkXNoCycle:
        return []


def assign_tiers(G: nx.DiGraph, root_entity_id: str) -> dict[str, int | None]:
    """Tier = BFS distance on the reverse graph: who supplies the root, then their suppliers.

    Tier 0 = the queried company.
    Tier 1 = direct suppliers.
    Tier 2 = suppliers of tier 1, and so on.

    Already-visited nodes are skipped, so a cycle cannot loop forever. Cyclic
    edges are still listed separately by detect_cycles().
    """
    tiers: dict[str, int | None] = {n: None for n in G.nodes}
    if root_entity_id not in G:
        return tiers
    reverse = G.reverse(copy=False)
    q = deque([(root_entity_id, 0)])
    seen = {root_entity_id}
    tiers[root_entity_id] = 0
    while q:
        node, dist = q.popleft()
        for pred in reverse.successors(node):
            if pred in seen:
                continue
            seen.add(pred)
            tiers[pred] = dist + 1
            q.append((pred, dist + 1))
    return tiers


def chain_subgraph(G: nx.DiGraph, root_entity_id: str, tiers: dict[str, int | None]) -> nx.DiGraph:
    keep = {n for n, t in tiers.items() if t is not None}
    return G.subgraph(keep).copy()
