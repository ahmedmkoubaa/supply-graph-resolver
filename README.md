# Supply graph resolver

Python pipeline that turns a noisy supplier↔customer CSV into a **resolved multi-tier graph**.

There is no companion notes file in this repo. The only input is `sentinel-supply-chain.csv` (7 relationship rows). It does **not** contain `NorthGate Textiles S.A. (España)`; use `--company` against a name that exists after resolution (default: `Global Alloys SARL`). `NORTHGATE TRADING SARL` is present as a France-based supplier of Horizon Alloys.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python app.py --csv sentinel-supply-chain.csv --company "Global Alloys SARL"
python app.py --company "NORTHGATE TRADING SARL"
```

Writes:

- `output/graph.json` — resolved graph for the queried company
- `output/graph.mmd` — Mermaid view
- `output/relationships_clean.csv` — original rows with normalized names, ISO countries, tax IDs, dates, and canonical entity ids
- `output/entities_clean.csv` — golden records (one row per resolved company)

## Layers

`parse → normalize → block → match → resolve → build_graph → assign_tiers → export`

- **Blocking:** ISO country + first two letters of the suffix-stripped name (not all-pairs).
- **Confidence:** `0.5 * name + 0.3 * tax_id + 0.2 * country`.
- **Merge if >85**, **flag 65–85** (no auto-merge), **distinct below 65**.
- **Tiers:** BFS upstream from the queried company. Tier 1 supplies the company; tier 2 supplies tier 1.
