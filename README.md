# Supply graph resolver

A layered Python entity-resolution pipeline plus an independent FastAPI and React application for exploring the noisy supplier↔customer CSV as a resolved multi-tier graph.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

## Run the existing CLI

```bash
python app.py --csv ecovadis_practice_supplier_data.csv --company "NorthGate Textiles S.A."
```

Writes:

- `output/graph.json` — resolved graph for the queried company
- `output/graph.mmd` — Mermaid view
- `output/relationships_clean.csv` — original rows with normalized names, ISO countries, tax IDs, dates, and canonical entity ids
- `output/entities_clean.csv` — golden records (one row per resolved company)

The CLI remains separate from the web server and can still be run on its own.

## Run the web application

Start the API from the repository root:

```bash
uvicorn backend.main:app --reload --port 8000
```

Then start the independent frontend in another terminal:

```bash
cd frontend
npm run dev
```

Vite proxies `/api` to FastAPI during development. For a separately deployed API, set `VITE_API_URL` (including the `/api` suffix). The API defaults to `ecovadis_practice_supplier_data.csv`; override it with `SUPPLY_GRAPH_CSV=/path/to/file.csv`.

### API endpoints

- `GET /api/summary` — dataset counts and status
- `GET /api/rows` — paginated/searchable raw rows
- `GET /api/entities` — paginated/searchable resolved entities
- `GET /api/relationships/clean` — paginated/searchable normalized relationships
- `GET /api/entities/{entity_id}/graph` — all upstream tiers for one resolved entity

The table endpoints accept `offset`, `limit` (maximum 200), and `query`. Startup only records the CSV path. Every uncached lookup reads and processes on demand, then releases its pandas/NetworkX working state. Only completed JSON responses are cached (and automatically bypassed when the CSV modification time changes), so repeated pages or entity graphs return quickly without keeping the full dataset graph resident.

## Layers

`parse → normalize → block → match → resolve → build_graph → assign_tiers → export`

- **Blocking:** ISO country + first two letters of the suffix-stripped name (not all-pairs).
- **Confidence:** `0.5 * name + 0.3 * tax_id + 0.2 * country`.
- **Merge if >85**, **flag 65–85** (no auto-merge), **distinct below 65**.
- **Tiers:** BFS upstream from the queried company. Tier 1 supplies the company; tier 2 supplies tier 1.
