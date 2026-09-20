"""Orchestrate parse → normalize → block → match → resolve → graph → export."""

from __future__ import annotations

from pathlib import Path

from rapidfuzz import fuzz

from .block import block
from .export import (
    clean_entities_frame,
    clean_relationships_frame,
    console_summary,
    json_safe,
    mermaid_diagram,
    to_payload,
    write_outputs,
)
from .graph import assign_tiers, build_graph, chain_subgraph, detect_cycles
from .match import match
from .normalize import explode_mentions, normalize_name, normalize_relationships
from .parse import parse, profile
from .resolve import resolve


def find_root_entity(entities, query: str | None):
    if entities.empty:
        return None
    if not query:
        # No query: use the company that appears most often as a customer.
        return entities.sort_values("mention_count", ascending=False).iloc[0]["entity_id"]
    q = normalize_name(query)["core_name"] or query.lower()
    best_id, best = None, -1.0
    for rec in entities.to_dict(orient="records"):
        score = fuzz.token_set_ratio(q, rec.get("core_name") or "")
        if rec.get("canonical_name") and fuzz.token_set_ratio(query.lower(), rec["canonical_name"].lower()) > score:
            score = fuzz.token_set_ratio(query.lower(), rec["canonical_name"].lower())
        if score > best:
            best, best_id = score, rec["entity_id"]
    if best < 70:
        names = ", ".join(entities["canonical_name"].astype(str))
        raise ValueError(
            f"Could not match company '{query}' to a resolved entity (best={best:.0f}). "
            f"Known entities: {names}"
        )
    return best_id


def run_pipeline(
    csv_path: str | Path,
    company: str | None = None,
    out_dir: str | Path = "output",
) -> dict:
    raw = parse(csv_path)
    print(profile(raw))
    print()

    relationships = normalize_relationships(raw)
    mentions = explode_mentions(raw)
    mentions = mentions[mentions["core_name"].notna()].reset_index(drop=True)

    blocks = block(mentions)
    scored = match(blocks)
    entities, flagged, mentions = resolve(mentions, scored)

    G_all = build_graph(relationships, mentions, entities)
    cycles = detect_cycles(G_all)
    root_id = find_root_entity(entities, company)
    tiers = assign_tiers(G_all, root_id) if root_id else {n: None for n in G_all.nodes}
    G = chain_subgraph(G_all, root_id, tiers) if root_id else G_all

    payload = to_payload(G, entities, flagged, tiers, root_id, cycles, n_raw_rows=len(raw))
    payload["all_resolved_entities"] = json_safe(entities.to_dict(orient="records"))
    mermaid = mermaid_diagram(G, tiers, root_id)
    relationships_clean = clean_relationships_frame(relationships, mentions, entities)
    entities_clean = clean_entities_frame(entities)
    paths = write_outputs(
        payload,
        mermaid,
        Path(out_dir),
        relationships_clean=relationships_clean,
        entities_clean=entities_clean,
    )
    print(console_summary(payload, paths))
    print()
    print("=== mermaid ===")
    print(mermaid)
    return {
        "raw": raw,
        "relationships": relationships,
        "mentions": mentions,
        "blocks": blocks,
        "scored": scored,
        "entities": entities,
        "flagged": flagged,
        "graph": G,
        "payload": payload,
        "mermaid": mermaid,
    }
