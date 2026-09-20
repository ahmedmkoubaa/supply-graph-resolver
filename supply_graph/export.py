"""export(): graph-ready JSON, console summary, Mermaid view."""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pandas as pd


def mermaid_diagram(G: nx.DiGraph, tiers: dict[str, int | None], root_id: str | None) -> str:
    lines = ["graph LR"]
    for nid, data in G.nodes(data=True):
        name = data.get("canonical_name") or nid
        tier = tiers.get(nid)
        label = f"{_esc(name)}\\n{nid}"
        if tier is not None:
            label += f"\\ntier {tier}"
        lines.append(f'  {nid}["{label}"]')
    for src, tgt, data in G.edges(data=True):
        rel = ",".join(data.get("relationship_types") or []) or "supplies"
        lines.append(f"  {src} -->|{_esc(rel)}| {tgt}")
    if root_id:
        lines.append(f"  classDef root fill:#d4f4dd,stroke:#1b7f3a;")
        lines.append(f"  class {root_id} root;")
    return "\n".join(lines)


def json_safe(value):
    """JSON has no NaN; missing fields become null."""
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _esc(text: str) -> str:
    return str(text).replace('"', "'")


def to_payload(
    G: nx.DiGraph,
    entities: pd.DataFrame,
    flagged: list[dict],
    tiers: dict[str, int | None],
    root_entity_id: str | None,
    cycles: list[list[str]],
    n_raw_rows: int,
) -> dict:
    nodes = []
    for rec in entities.to_dict(orient="records"):
        if rec["entity_id"] not in G:
            continue
        item = dict(rec)
        item["tier"] = tiers.get(rec["entity_id"])
        item["is_root"] = rec["entity_id"] == root_entity_id
        nodes.append(item)
    edges = []
    for src, tgt, data in G.edges(data=True):
        edges.append(
            {
                "source": src,
                "target": tgt,
                "confidence": data.get("confidence"),
                "tier": tiers.get(src),  # supplier's distance from the queried company
                "relationship_types": data.get("relationship_types"),
                "source_rows": data.get("source_rows"),
            }
        )
    return json_safe({
        "root_entity_id": root_entity_id,
        "nodes": nodes,
        "edges": edges,
        "flagged_for_review": flagged,
        "cycles": cycles,
        "summary": {
            "rows_processed": n_raw_rows,
            "entities_resolved": len(nodes),
            "relationships": len(edges),
            "flagged_cases": len(flagged),
            "relationships_per_tier": _counts_by_tier(edges),
        },
    })


def _counts_by_tier(edges: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in edges:
        key = str(e.get("tier"))
        counts[key] = counts.get(key, 0) + 1
    return counts


CLEAN_RELATIONSHIP_COLUMNS = [
    "row_id",
    "source_system",
    "customer_entity_id",
    "customer_canonical_name",
    "customer_core_name",
    "customer_suffix",
    "customer_tax_id",
    "customer_country",
    "supplier_entity_id",
    "supplier_canonical_name",
    "supplier_core_name",
    "supplier_suffix",
    "supplier_tax_id",
    "supplier_country",
    "relationship_type_norm",
    "last_updated_iso",
    "notes",
]


def _entity_lookup(mentions: pd.DataFrame, entities: pd.DataFrame, role: str) -> pd.DataFrame:
    m = mentions.loc[mentions["role"] == role, ["row_id", "entity_id"]].copy()
    m["row_id"] = m["row_id"].astype(str)
    ent = entities.rename(columns={"entity_id": f"{role}_entity_id", "canonical_name": f"{role}_canonical_name"})
    merged = m.merge(ent[[f"{role}_entity_id", f"{role}_canonical_name"]], left_on="entity_id", right_on=f"{role}_entity_id", how="left")
    return merged[["row_id", f"{role}_entity_id", f"{role}_canonical_name"]].drop_duplicates("row_id")


def clean_relationships_frame(relationships: pd.DataFrame, mentions: pd.DataFrame, entities: pd.DataFrame) -> pd.DataFrame:
    """Original rows, cleaned fields, plus resolved canonical entity ids/names."""
    out = relationships.copy()
    out["row_id"] = out["row_id"].astype(str)
    customers = _entity_lookup(mentions, entities, "customer")
    suppliers = _entity_lookup(mentions, entities, "supplier")
    out = out.merge(customers, on="row_id", how="left")
    out = out.merge(suppliers, on="row_id", how="left")
    present = [c for c in CLEAN_RELATIONSHIP_COLUMNS if c in out.columns]
    return out[present]


def clean_entities_frame(entities: pd.DataFrame) -> pd.DataFrame:
    out = entities.copy()
    if "raw_variants" in out.columns:
        out["raw_variants"] = out["raw_variants"].map(
            lambda v: " | ".join(v) if isinstance(v, list) else v
        )
    return out


def write_outputs(
    payload: dict,
    mermaid: str,
    out_dir: Path,
    relationships_clean: pd.DataFrame | None = None,
    entities_clean: pd.DataFrame | None = None,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": out_dir / "graph.json",
        "mermaid": out_dir / "graph.mmd",
        "relationships_csv": out_dir / "relationships_clean.csv",
        "entities_csv": out_dir / "entities_clean.csv",
    }
    paths["json"].write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    paths["mermaid"].write_text(mermaid, encoding="utf-8")
    if relationships_clean is not None:
        relationships_clean.to_csv(paths["relationships_csv"], index=False)
    if entities_clean is not None:
        entities_clean.to_csv(paths["entities_csv"], index=False)
    return paths


def console_summary(payload: dict, paths: dict | None = None) -> str:
    s = payload["summary"]
    lines = [
        "=== supply graph summary ===",
        f"rows processed:        {s['rows_processed']}",
        f"entities resolved:     {s['entities_resolved']}",
        f"relationships:         {s['relationships']}",
        f"flagged_for_review:    {s['flagged_cases']}",
        f"relationships/tier:    {s['relationships_per_tier']}",
        f"root entity:           {payload.get('root_entity_id')}",
        f"cycles flagged:        {len(payload.get('cycles') or [])}",
    ]
    if paths:
        lines.append("wrote:")
        for key in ("json", "mermaid", "relationships_csv", "entities_csv"):
            if key in paths:
                lines.append(f"  {paths[key]}")
    return "\n".join(lines)
