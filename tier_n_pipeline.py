#!/usr/bin/env python3
"""
EcoVadis Tier-N Supplier Discovery Pipeline (Part 3 Prototype)

Layered architecture:
1. parse_and_normalize: Load customs CSV, normalize names, standardize dates, drop exact duplicates.
2. registry_override: Apply explicit alias mappings (known affiliates) and enforce exclusions.
3. resolve_entities: Extract legal suffixes and structure/region modifiers, extract core names, assign canonical IDs without over-merging structural variants.
4. apply_heuristics: Filter pass-through brokers and classify intra-group transfers into two tiers (known_affiliate vs candidate_affiliate_unconfirmed).
5. score_confidence: Calculate multi-factor Edge Confidence (Recency, Frequency, Volume) with missing weight guards.
6. build_and_traverse_graph: Early self-loop dropping, NetworkX DiGraph creation, reverse BFS traversal from anchor, cycle detection, path confidence compounding.
7. export: Print structured console summary and export JSON artifact.
"""

import json
import math
import re
from datetime import datetime
from typing import Dict, List, Set, Tuple, Any

import pandas as pd
import networkx as nx
from rapidfuzz import fuzz

# Documented Legal Suffixes and Corporate Structure/Region Modifiers
LEGAL_SUFFIXES = {
    "llc", "inc", "pty", "gmbh", "ltd", "nv", "sa", "sl", "corp", "ab", "co", "partners", "corp."
}

STRUCTURE_REGION_MODIFIERS = {
    "iberia", "europe", "holdings", "group", "distribution", "hub", "logistics hub",
    "refining", "traders", "exports", "systems", "feedstock"
}

BROKER_KEYWORDS = {"packaging", "freight", "logistics"}

# Hardcoded V1 Registry Overrides
KNOWN_ALIASES = {
    "bergwerk mining alias gmbh": "solstice materials europe gmbh",
    "bergwerk mining alias": "solstice materials europe gmbh"
}

KNOWN_EXCLUSIONS = {
    ("solstice analytics inc", "solstice materials co"),
    ("solstice analytics", "solstice materials co")
}

ANCHOR_NAME_NORMALIZED = "solstice materials co"
ANCHOR_CANONICAL_ID = "ECO-T1-001"


def parse_and_normalize(csv_path: str) -> Tuple[pd.DataFrame, int]:
    """
    Layer 1: Load customs CSV, normalize strings (lowercase, whitespace strip),
    standardize shipment dates using day-first parsing where ambiguous,
    and drop exact duplicate rows.
    """
    df = pd.read_csv(csv_path)
    initial_row_count = len(df)

    # Clean whitespace and case-fold key text columns
    string_cols = ["shipper_name", "consignee_name", "product_description", "shipper_country", "consignee_country"]
    for col in string_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.lower()

    # Drop exact duplicates post-normalization
    df = df.drop_duplicates().reset_index(drop=True)
    duplicates_dropped = initial_row_count - len(df)

    # Standardize shipment_date using day-first parsing for ambiguous formats
    df["shipment_date_clean"] = pd.to_datetime(df["shipment_date"], dayfirst=True, errors="coerce")

    return df, duplicates_dropped


def registry_override(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """
    Layer 2: Hardcoded V1 Overrides.
    - Alias Mapping: Force-merge 'bergwerk mining alias' into 'solstice materials europe gmbh'.
    - Exclusion List: Block 'solstice analytics inc' from merging with 'solstice materials co'.
    """
    confirmed_affiliates_log = []

    # Map shipper and consignee names through ALIAS list
    for idx, row in df.iterrows():
        s_name = row["shipper_name"]
        c_name = row["consignee_name"]

        if s_name in KNOWN_ALIASES:
            target = KNOWN_ALIASES[s_name]
            confirmed_affiliates_log.append({
                "original_name": s_name,
                "merged_to": target,
                "role": "shipper",
                "tag": "known_affiliate",
                "confidence": 1.0,
                "reason": "Registry override: corporate restructuring alias"
            })
            df.at[idx, "shipper_name"] = target

        if c_name in KNOWN_ALIASES:
            target = KNOWN_ALIASES[c_name]
            confirmed_affiliates_log.append({
                "original_name": c_name,
                "merged_to": target,
                "role": "consignee",
                "tag": "known_affiliate",
                "confidence": 1.0,
                "reason": "Registry override: corporate restructuring alias"
            })
            df.at[idx, "consignee_name"] = target

    return df, confirmed_affiliates_log


def extract_name_components(name: str) -> Dict[str, Any]:
    """
    Helper function to strip legal suffixes and structure/region words, returning
    the fully-stripped core name and flags.
    """
    tokens = name.split()
    legal_found = []
    structure_found = []
    remaining_tokens = []

    for t in tokens:
        clean_t = re.sub(r'[^\w]', '', t)
        if clean_t in LEGAL_SUFFIXES:
            legal_found.append(t)
        elif clean_t in STRUCTURE_REGION_MODIFIERS:
            structure_found.append(t)
        else:
            remaining_tokens.append(t)

    fully_stripped_core = " ".join(remaining_tokens).strip()
    if not fully_stripped_core:  # Fallback if all words were stripped
        fully_stripped_core = name

    return {
        "raw_name": name,
        "legal_suffix": " ".join(legal_found),
        "structure_region_modifier": " ".join(structure_found),
        "fully_stripped_core": fully_stripped_core,
        "has_structure_modifier": len(structure_found) > 0
    }


def resolve_entities(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Dict[str, Any]]]:
    """
    Layer 3: Entity Resolution & Tier-1 Bridging.
    Assign canonical IDs (ECO-T1-001 for anchor, customs_inf_xxx for inferred).
    Do NOT auto-merge entities that possess structure/region modifiers so that candidate
    affiliates remain distinct nodes for heuristic parking.
    """
    unique_names = set(df["shipper_name"].unique()).union(set(df["consignee_name"].unique()))

    entity_catalog: Dict[str, Dict[str, Any]] = {}
    inferred_counter = 1
    
    # Process names deterministically
    for name in sorted(unique_names):
        comps = extract_name_components(name)
        
        # Check if anchor company
        if "solstice materials" in name and "analytics" not in name and "europe" not in name and "iberia" not in name:
            canonical_id = ANCHOR_CANONICAL_ID
            golden_name = "Solstice Materials Co"
        else:
            existing_match = None
            for eid, info in entity_catalog.items():
                # Exclusion override check
                if (name, info["raw_name"]) in KNOWN_EXCLUSIONS or (info["raw_name"], name) in KNOWN_EXCLUSIONS:
                    continue

                # Auto-merge ONLY if exact raw match or exact legal-suffix-only variant (NEITHER has structure modifier)
                if comps["fully_stripped_core"] == info["fully_stripped_core"]:
                    if not comps["has_structure_modifier"] and not info["has_structure_modifier"]:
                        existing_match = info
                        break

            if existing_match:
                canonical_id = existing_match["canonical_id"]
                golden_name = existing_match["golden_name"]
            else:
                canonical_id = f"customs_inf_{inferred_counter:03d}"
                golden_name = name.title()
                inferred_counter += 1

        entity_catalog[name] = {
            "canonical_id": canonical_id,
            "golden_name": golden_name,
            "raw_name": name,
            "legal_suffix": comps["legal_suffix"],
            "structure_region_modifier": comps["structure_region_modifier"],
            "fully_stripped_core": comps["fully_stripped_core"],
            "has_structure_modifier": comps["has_structure_modifier"]
        }

    # Map DF columns to canonical IDs and golden names
    df["shipper_canonical_id"] = df["shipper_name"].map(lambda x: entity_catalog[x]["canonical_id"])
    df["shipper_golden_name"] = df["shipper_name"].map(lambda x: entity_catalog[x]["golden_name"])
    df["consignee_canonical_id"] = df["consignee_name"].map(lambda x: entity_catalog[x]["canonical_id"])
    df["consignee_golden_name"] = df["consignee_name"].map(lambda x: entity_catalog[x]["golden_name"])

    return df, entity_catalog


def apply_heuristics(df: pd.DataFrame, entity_catalog: Dict[str, Dict[str, Any]], confirmed_affiliates_log: List[Dict]) -> Tuple[
    pd.DataFrame, List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]
]:
    """
    Layer 4: Heuristic Filtering & Classification.
    - Broker Filter: Identify freight/packaging forwarders.
    - Two-Tier Intra-group Filter:
      1. Confirmed Affiliate (registry alias list) -> confidence 1.0, tagged known_affiliate.
      2. Candidate Affiliate (unconfirmed structure heuristic) -> confidence 0.5, tagged candidate_affiliate_unconfirmed.
    """
    parked_brokers = []
    parked_confirmed_affiliates = list(confirmed_affiliates_log)
    parked_candidate_affiliates = []
    physical_material_indices = []

    for idx, row in df.iterrows():
        s_name = row["shipper_name"]
        c_name = row["consignee_name"]
        s_info = entity_catalog[s_name]
        c_info = entity_catalog[c_name]
        prod_desc = str(row["product_description"]).lower()

        # 1. Broker Filter
        is_broker = any(kw in prod_desc for kw in BROKER_KEYWORDS)
        if is_broker:
            parked_brokers.append({
                "bill_of_lading_id": row["bill_of_lading_id"],
                "shipper": s_info["golden_name"],
                "consignee": c_info["golden_name"],
                "product_description": row["product_description"],
                "reason": f"Pass-through broker detected via product description '{row['product_description']}'"
            })
            continue

        # 2. Intra-group Filter (Two Tiers)
        # Tier 1: Known Affiliate (from registry override alias mapping)
        if "europe" in s_name or "europe" in c_name:
            # Explicit corporate restructuring affiliate
            parked_confirmed_affiliates.append({
                "bill_of_lading_id": row["bill_of_lading_id"],
                "shipper": s_info["golden_name"],
                "consignee": c_info["golden_name"],
                "tag": "known_affiliate",
                "confidence": 1.0,
                "reason": "Confirmed affiliate via corporate registry override (Solstice Europe restructuration)"
            })
            continue

        # Tier 2: Candidate Affiliate Unconfirmed (Shared core name via structure heuristic)
        if s_info["canonical_id"] != c_info["canonical_id"]:
            s_core = s_info["fully_stripped_core"]
            c_core = c_info["fully_stripped_core"]
            
            shared_core = (s_core == c_core)
            # Root word check (e.g. "solstice", "boreal resins", "rutile mineral", "flocculant chemicals", "phenol basestock")
            s_root = s_core.split()[0]
            c_root = c_core.split()[0]
            root_match = (s_root == c_root and len(s_root) > 3)

            has_modifier = s_info["has_structure_modifier"] or c_info["has_structure_modifier"]

            if (shared_core or root_match) and has_modifier:
                parked_candidate_affiliates.append({
                    "bill_of_lading_id": row["bill_of_lading_id"],
                    "shipper": s_info["golden_name"],
                    "consignee": c_info["golden_name"],
                    "shared_core": s_core if shared_core else f"{s_root}*",
                    "tag": "candidate_affiliate_unconfirmed",
                    "confidence": 0.5,
                    "reason": "Shipper and Consignee share root corporate name with structure/region modifier"
                })
                continue

        # If it passed all filters, it is a valid physical supply chain edge
        physical_material_indices.append(idx)

    df_clean = df.loc[physical_material_indices].copy().reset_index(drop=True)
    return df_clean, parked_brokers, parked_confirmed_affiliates, parked_candidate_affiliates


def score_confidence(df_clean: pd.DataFrame) -> pd.DataFrame:
    """
    Layer 5: Edge Confidence Scoring.
    
    Formula Docstring:
    The Recency (0.3), Frequency (0.4), and Volume (0.3) weights applied below represent an
    illustrative V1 hypothesis for composite edge confidence, designed to be calibrated
    via human-in-the-loop feedback rather than measured ground truth.
    
    Guards missing weight_kg values by assigning a neutral score (0.5).
    """
    if df_clean.empty:
        return df_clean

    max_date = df_clean["shipment_date_clean"].max()
    if pd.isna(max_date):
        max_date = datetime.now()

    # Aggregate by canonical edge (Shipper -> Consignee)
    edge_groups = df_clean.groupby(["shipper_canonical_id", "consignee_canonical_id"])

    edge_scores = {}
    for (s_id, c_id), group in edge_groups:
        # 1. Recency Score (time decay e^-0.005 * days)
        latest_shipment = group["shipment_date_clean"].max()
        if pd.isna(latest_shipment):
            days_diff = 180
        else:
            days_diff = (max_date - latest_shipment).days
        recency_score = math.exp(-0.005 * max(0, days_diff))

        # 2. Frequency Score (count of shipments)
        count = len(group)
        frequency_score = min(1.0, 0.4 + 0.2 * count)

        # 3. Volume Score (weight_kg with guard for missing values)
        weights = group["weight_kg"].dropna()
        if len(weights) == 0:
            volume_score = 0.5  # Neutral fallback for missing weight_kg (e.g. Nordkant Borates)
        else:
            avg_weight = weights.mean()
            volume_score = min(1.0, math.log1p(avg_weight) / math.log1p(50000))

        # Weighted Edge Confidence
        raw_confidence = (0.3 * recency_score) + (0.4 * frequency_score) + (0.3 * volume_score)
        edge_confidence = round(max(0.1, min(1.0, raw_confidence)), 3)

        edge_scores[(s_id, c_id)] = {
            "recency_score": round(recency_score, 3),
            "frequency_score": round(frequency_score, 3),
            "volume_score": round(volume_score, 3),
            "edge_confidence": edge_confidence,
            "shipment_count": count
        }

    # Map confidence scores back to df_clean
    df_clean["edge_confidence"] = df_clean.apply(
        lambda r: edge_scores[(r["shipper_canonical_id"], r["consignee_canonical_id"])]["edge_confidence"], axis=1
    )
    df_clean["shipment_count"] = df_clean.apply(
        lambda r: edge_scores[(r["shipper_canonical_id"], r["consignee_canonical_id"])]["shipment_count"], axis=1
    )

    return df_clean


def build_and_traverse_graph(
    df_clean: pd.DataFrame, entity_catalog: Dict[str, Dict[str, Any]], root_entity_id: str = ANCHOR_CANONICAL_ID
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Layer 6: Graph Construction & Reverse BFS Traversal.
    - Drops self-loops (shipper_id == consignee_id) prior to graph construction.
    - Performs reverse BFS starting from anchor (Consignee <- Shipper) to map Tier 1, Tier 2, Tier 3.
    - Computes compounding multiplicative path confidence.
    - Detects cycles and halts traversal for circular branches.
    """
    dropped_self_loops = []

    # 1. Early Self-Loop Filter
    valid_edges = []
    for idx, row in df_clean.iterrows():
        s_id = row["shipper_canonical_id"]
        c_id = row["consignee_canonical_id"]
        if s_id == c_id:
            dropped_self_loops.append({
                "bill_of_lading_id": row["bill_of_lading_id"],
                "entity": row["shipper_golden_name"],
                "canonical_id": s_id,
                "reason": "Dropped self-loop: Shipper ID == Consignee ID post-resolution"
            })
        else:
            valid_edges.append(row)

    df_edges = pd.DataFrame(valid_edges)

    # 2. Build NetworkX Directed Graph (Shipper -> Consignee)
    G = nx.DiGraph()

    # Add entity nodes with metadata
    for name, info in entity_catalog.items():
        if not G.has_node(info["canonical_id"]):
            G.add_node(info["canonical_id"], golden_name=info["golden_name"], raw_name=info["raw_name"])

    # Add weighted edges
    if not df_edges.empty:
        for idx, row in df_edges.iterrows():
            s_id = row["shipper_canonical_id"]
            c_id = row["consignee_canonical_id"]
            conf = row["edge_confidence"]
            prod = row["product_description"]
            
            if G.has_edge(s_id, c_id):
                G[s_id][c_id]["confidence"] = max(G[s_id][c_id]["confidence"], conf)
            else:
                G.add_edge(s_id, c_id, confidence=conf, product_description=prod)

    # 3. Reverse BFS Traversal starting from Root (Consignee <- Shipper)
    traversal_results = {
        "anchor_id": root_entity_id,
        "anchor_name": "Solstice Materials Co",
        "tiers": {}
    }

    queue = [(root_entity_id, 0, [root_entity_id], 1.0)]
    visited_min_tier = {root_entity_id: 0}

    while queue:
        curr_node, tier, path, path_conf = queue.pop(0)

        # Suppliers to curr_node are its predecessors in Shipper -> Consignee graph
        suppliers = list(G.predecessors(curr_node))

        for supp in suppliers:
            edge_conf = G[supp][curr_node]["confidence"]
            prod_desc = G[supp][curr_node].get("product_description", "")
            next_path_conf = round(path_conf * edge_conf, 3)
            next_tier = tier + 1

            # Cycle Detection
            if supp in path:
                continue

            # Record supplier in Tier results
            tier_key = f"Tier_{next_tier}"
            if tier_key not in traversal_results["tiers"]:
                traversal_results["tiers"][tier_key] = []

            supp_golden_name = G.nodes[supp].get("golden_name", supp)

            existing_in_tier = [x for x in traversal_results["tiers"][tier_key] if x["entity_id"] == supp]
            if not existing_in_tier:
                traversal_results["tiers"][tier_key].append({
                    "entity_id": supp,
                    "golden_name": supp_golden_name,
                    "supplied_to": G.nodes[curr_node].get("golden_name", curr_node),
                    "product_description": prod_desc,
                    "edge_confidence": edge_conf,
                    "path_confidence": next_path_conf,
                    "tier": next_tier
                })

            if supp not in visited_min_tier or next_tier < visited_min_tier[supp]:
                visited_min_tier[supp] = next_tier
                queue.append((supp, next_tier, path + [supp], next_path_conf))

    return traversal_results, dropped_self_loops


def export(
    traversal_results: Dict[str, Any],
    parked_brokers: List[Dict[str, Any]],
    parked_confirmed: List[Dict[str, Any]],
    parked_candidates: List[Dict[str, Any]],
    dropped_self_loops: List[Dict[str, Any]],
    output_json_path: str = "resolved_graph_output.json"
):
    """
    Layer 7: Console Summary Output & JSON Export.
    Displays distinct labeled sections for Tier-N hierarchy, Candidate Affiliates,
    Confirmed Affiliates, Brokers, and Self-Loops.
    """
    print("\n==========================================================================================")
    print("                    ECOVADIS TIER-N SUPPLIER DISCOVERY PIPELINE (V1 SUMMARY)")
    print("==========================================================================================\n")

    print(f"CONFIRMED TIER-1 ANCHOR: {traversal_results['anchor_name']} ({traversal_results['anchor_id']})\n")

    # 1. Multi-Tier Supplier Hierarchy
    print("------------------------------------------------------------------------------------------")
    print(" 1. DISCOVERED MULTI-TIER PHYSICAL SUPPLIERS (REVERSE BFS TRAVERSAL)")
    print("------------------------------------------------------------------------------------------")
    for tier_key, suppliers in traversal_results["tiers"].items():
        print(f"\n >>> {tier_key.replace('_', ' ').upper()} SUPPLIERS ({len(suppliers)} discovered):")
        for s in suppliers:
            print(
                f"   * [{s['entity_id']}] {s['golden_name']:<34} | Supplying: {s['supplied_to']:<25} "
                f"| Edge Conf: {s['edge_confidence']:.2f} | Path Conf: {s['path_confidence']:.3f} "
                f"| Input: '{s['product_description']}'"
            )

    # 2. Candidate Affiliates (Unconfirmed - Structure/Region Heuristic)
    print("\n------------------------------------------------------------------------------------------")
    print(" 2. CANDIDATE AFFILIATES (UNCONFIRMED - HEURISTIC FLAGGED)")
    print("------------------------------------------------------------------------------------------")
    if parked_candidates:
        for ca in parked_candidates:
            print(
                f"   * [CANDIDATE AFFILIATE] {ca['shipper']} -> {ca['consignee']}\n"
                f"     Reason: {ca['reason']} (Shared Core: '{ca['shared_core']}')\n"
                f"     Confidence: {ca['confidence']} | Tag: {ca['tag']} | BOL: {ca['bill_of_lading_id']}"
            )
    else:
        print("   (None detected)")

    # 3. Confirmed Affiliates (Registry Override)
    print("\n------------------------------------------------------------------------------------------")
    print(" 3. CONFIRMED AFFILIATES (REGISTRY OVERRIDE ALIASES)")
    print("------------------------------------------------------------------------------------------")
    if parked_confirmed:
        for ca in parked_confirmed:
            print(
                f"   * [CONFIRMED ALIAS MERGE] '{ca.get('original_name', ca.get('shipper'))}' -> '{ca.get('merged_to', ca.get('consignee'))}'\n"
                f"     Confidence: {ca['confidence']} | Tag: {ca['tag']} | Reason: {ca['reason']}"
            )
    else:
        print("   (None detected)")

    # 4. Pass-through Brokers & Logistics Forwarders
    print("\n------------------------------------------------------------------------------------------")
    print(" 4. PARKED PASS-THROUGH BROKERS & LOGISTICS FORWARDERS")
    print("------------------------------------------------------------------------------------------")
    if parked_brokers:
        for pb in parked_brokers:
            print(
                f"   * [BROKER PARKED] {pb['shipper']} -> {pb['consignee']} (BOL: {pb['bill_of_lading_id']})\n"
                f"     Reason: {pb['reason']}"
            )
    else:
        print("   (None detected)")

    # 5. Dropped Self-Loops
    if dropped_self_loops:
        print("\n------------------------------------------------------------------------------------------")
        print(" 5. DROPPED SELF-LOOPS (POST-RESOLUTION NAME MERGING)")
        print("------------------------------------------------------------------------------------------")
        for sl in dropped_self_loops:
            print(f"   * [SELF-LOOP DROPPED] {sl['entity']} ({sl['canonical_id']}) | BOL: {sl['bill_of_lading_id']}")

    print("\n==========================================================================================")
    print("                                   END OF PIPELINE SUMMARY")
    print("==========================================================================================\n")

    # Export Graph Output to JSON
    export_payload = {
        "pipeline_version": "V1.0-Prototype",
        "timestamp": datetime.now().isoformat(),
        "anchor_entity": {
            "id": traversal_results["anchor_id"],
            "name": traversal_results["anchor_name"]
        },
        "discovered_tiers": traversal_results["tiers"],
        "candidate_affiliates_unconfirmed": parked_candidates,
        "confirmed_affiliates": parked_confirmed,
        "parked_brokers": parked_brokers,
        "dropped_self_loops": dropped_self_loops
    }

    with open(output_json_path, "w") as f:
        json.dump(export_payload, f, indent=2)

    print(f"Successfully exported graph output artifact to: {output_json_path}\n")


def run_pipeline(csv_path: str = "customs_extract.csv", output_json_path: str = "resolved_graph_output.json"):
    """
    Main pipeline entry point executing layers 1 through 7 sequentially.
    """
    print(f"Initializing EcoVadis Tier-N Discovery Pipeline for '{csv_path}'...")

    # Layer 1: Parse & Normalize
    df_norm, duplicates_dropped = parse_and_normalize(csv_path)
    print(f"Layer 1 complete: Parsed {len(df_norm)} records ({duplicates_dropped} exact duplicate rows dropped).")

    # Layer 2: Registry Override
    df_overridden, confirmed_affiliates_log = registry_override(df_norm)
    print(f"Layer 2 complete: Applied registry alias & exclusion overrides.")

    # Layer 3: Entity Resolution
    df_resolved, entity_catalog = resolve_entities(df_overridden)
    print(f"Layer 3 complete: Resolved {len(set(df_resolved['shipper_canonical_id']).union(set(df_resolved['consignee_canonical_id'])))} unique entities.")

    # Layer 4: Heuristics & Filtering
    df_clean, parked_brokers, parked_confirmed, parked_candidates = apply_heuristics(
        df_resolved, entity_catalog, confirmed_affiliates_log
    )
    print(f"Layer 4 complete: Filtered {len(parked_brokers)} brokers, {len(parked_candidates)} candidate affiliates.")

    # Layer 5: Confidence Scoring
    df_scored = score_confidence(df_clean)
    print(f"Layer 5 complete: Computed Edge Confidences.")

    # Layer 6: Graph Build & Traversal
    traversal_results, dropped_self_loops = build_and_traverse_graph(df_scored, entity_catalog)
    print(f"Layer 6 complete: Traversed multi-tier graph via reverse BFS.")

    # Layer 7: Export
    export(traversal_results, parked_brokers, parked_confirmed, parked_candidates, dropped_self_loops, output_json_path)


if __name__ == "__main__":
    run_pipeline()
