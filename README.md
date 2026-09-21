# EcoVadis Tier-N Supplier Discovery Pipeline

A modular Python solution for discovering deep-tier ($T_1, T_2, T_3, \dots, T_N$) supply chain relationships from messy ocean shipment customs data (`customs_extract.csv`), anchored at EcoVadis confirmed Tier-1 supplier **Solstice Materials Co**.

---

## Deliverables & Documentation Index

- **[Part 1: Trade-Off Memo](documents/trade-off-memo.md):** Evaluation of customs trade data as a Tier-N signal (Coverage, Noise, Confidence, and Build vs. Buy).
- **[Part 2: Architecture & Heuristics Sketch](documents/architecture_heuristics_sketch.md):** Pipeline mapping table, edge confidence formula, and system diagrams.
- **[Part 3: Working Prototype Script](tier_n_pipeline.py):** Layered Python pipeline script implementing entity resolution and graph traversal.
- **[Part 4: Wrap-Up & Next Steps](documents/wrap-up.md):** Pre-ship testing recommendations and Version 2 roadmap items.
- **[Graph Output Artifact](resolved_graph_output.json):** Graph-ready JSON export containing nodes, edges, tiers, and audit tags.

---

## Executive Summary

EcoVadis tracks confirmed Tier-1 buyer-supplier relationships. However, deeper supply chain tiers ($T_2, T_3, \dots$) are rarely self-reported. This pipeline ingests public ocean shipment bills of lading (shippers and consignees) to infer multi-tier supplier relationships backwards up the supply chain while handling messy real-world data artifacts: misspelled corporate names, pass-through brokers, structural regional affiliates, missing attributes, and potential graph cycles.

---

## Summary of Case Study Sections

### Part 1: Trade-Off Memo
For full details, see [`documents/trade-off-memo.md`](documents/trade-off-memo.md).
- **Why Customs Data?** Reaches past Tier 1 without self-reporting.
- **The Three Costs:** Coverage (ocean US only), Noise (renames, forwarders), Confidence (unconfirmed compounding decay).
- **Build vs. Buy:** Use free customs data to validate buyer demand; upgrade to paid APIs (Panjiva/ImportGenius) to expand air/land coverage.

### Part 2: Architecture & Heuristics Sketch
For full details, see [`documents/architecture_heuristics_sketch.md`](documents/architecture_heuristics_sketch.md).
- **Layered Pipeline:** Ingestion $\rightarrow$ Overrides $\rightarrow$ Entity Resolution $\rightarrow$ Domain Heuristics $\rightarrow$ Confidence Scoring $\rightarrow$ BFS Traversal $\rightarrow$ Export.
- **Edge Confidence Formula:** $(0.3 \times \text{Recency}) + (0.4 \times \text{Frequency}) + (0.3 \times \text{Volume})$.

### Part 3: Working Prototype
Executable script [`tier_n_pipeline.py`](tier_n_pipeline.py) traversing 4 tiers backwards from anchor `Solstice Materials Co` (`ECO-T1-001`).

### Part 4: Wrap-Up & Next Steps
For full details, see [`documents/wrap-up.md`](documents/wrap-up.md).
- **Pre-Ship Instrumenting:** Human-in-the-Loop accept/reject feedback mechanism for confidence calibration; vertical precision/recall baselining.
- **Punted to V2:** Dynamic corporate registry API integration (OpenCorporates/D&B) and multi-modal coverage (air, rail, cross-border trucking).

---

## Discovered Multi-Tier Supply Chain Results

| Tier | Canonical ID | Supplier Golden Name | Supplied To | Input Product | Edge Conf. | Path Conf. |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **$T_1$** | `customs_inf_006` | **Boreal Resins Inc** | Solstice Materials Co | Epoxy Resin Compound | 0.89 | **0.892** |
| **$T_1$** | `customs_inf_025` | **Terra Silica Partners** | Solstice Materials Co | Silica Sand | 0.81 | **0.814** |
| **$T_1$** | `customs_inf_003` | **Aurora Pigments Ltd** | Solstice Materials Co | Titanium Dioxide Pigment | 0.78 | **0.779** |
| **$T_1$** | `customs_inf_012` | **Nordkant Borates AB** | Solstice Materials Co | Borate Compound | 0.73 | **0.729** |
| **$T_1$** | `customs_inf_011` | **Meridian Coatings LLC** | Solstice Materials Co | Industrial Coating Additive | 0.63 | **0.631** |
| **$T_1$** | `customs_inf_021` | **Solstice Analytics Inc** | Solstice Materials Co | Laboratory Testing Reagents | 0.61 | **0.609** |
| **$T_2$** | `customs_inf_014` | **Petrochem Feedstock LLC** | Boreal Resins Inc | Bisphenol-A Precursor | 0.76 | **0.676** |
| **$T_2$** | `customs_inf_017` | **Quartz Extraction Co** | Terra Silica Partners | Raw Quartz | 0.66 | **0.537** |
| **$T_2$** | `customs_inf_019` | **Rutile Mineral Exports Pty** | Aurora Pigments Ltd | Titanium Ore Concentrate | 0.63 | **0.488** |
| **$T_3$** | `customs_inf_015` | **Phenol Basestock Corp** | Petrochem Feedstock LLC | Phenol Feedstock | 0.73 | **0.491** |
| **$T_3$** | `customs_inf_009` | **Flocculant Chemicals Pty** | Rutile Mineral Exports Pty | Ore-Processing Flocculant Reagent | 0.73 | **0.356** |
| **$T_4$** | `customs_inf_004` | **Benzene Feedstock Refining Co** | Phenol Basestock Corp | Benzene Feedstock | 0.66 | **0.322** |
| **$T_4$** | `customs_inf_001` | **Acrylamide Monomer Pty** | Flocculant Chemicals Pty | Acrylamide Monomer | 0.66 | **0.234** |

---

## Parked Non-Physical & Intra-Group Entities

### Candidate Affiliates (Unconfirmed - Heuristic Flagged @ 0.5 Confidence)
- `Rutile Mineral Holdings Pty` $\rightarrow$ `Rutile Mineral Exports Pty` (Shared root: `rutile mineral`)
- `Petrochem Feedstock Distribution LLC` $\rightarrow$ `Petrochem Feedstock LLC` (Shared root: `petrochem`)
- `Solstice Materials Iberia SA` $\rightarrow$ `Solstice Materials Co` (Shared root: `solstice materials`)
- `Flocculant Chemicals Group Pty` $\rightarrow$ `Flocculant Chemicals Pty` (Shared root: `flocculant chemicals`)
- `Aurora Pigments Distribution GmbH` $\rightarrow$ `Aurora Pigments Ltd` (Shared root: `aurora pigments`)
- `Boreal Resins Iberia SL` $\rightarrow$ `Boreal Resins Inc` (Shared root: `boreal resins`)
- `Phenol Basestock Holdings Corp` $\rightarrow$ `Phenol Basestock Corp` (Shared root: `phenol basestock`)

### Confirmed Affiliates (Registry Override @ 1.0 Confidence)
- `Bergwerk Mining Alias GmbH` $\rightarrow$ `Solstice Materials Europe GmbH` $\rightarrow$ `Solstice Materials Co`

### Pass-Through Brokers & Forwarders
- `Global Cargo Solutions LLC` $\rightarrow$ `Solstice Materials Co` (Product: `packaging materials`)
- `Solstice Logistics Hub LLC` $\rightarrow$ `Solstice Materials Co` (Product: `packaging materials`)

---

## How to Run

### Requirements
- Python 3.9+
- `pandas`, `rapidfuzz`, `networkx`

### Setup & Execution

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install pandas rapidfuzz networkx

# Run the pipeline
python tier_n_pipeline.py
```

---

## File Structure

```text
supply-graph-resolver/
├── README.md                              # Main project documentation & deliverable index
├── documents/
│   ├── trade-off-memo.md                  # Part 1: Trade-off Memo
│   ├── architecture_heuristics_sketch.md  # Part 2: Architecture & Heuristics Sketch
│   └── wrap-up.md                         # Part 4: Wrap-Up & Next Steps
├── tier_n_pipeline.py                     # Part 3: Python pipeline prototype
├── customs_extract.csv                    # Ingestion ocean shipment dataset
├── corporate_registry_notes.txt           # Facts & ground-truth companion reference
└── resolved_graph_output.json             # Output graph JSON artifact
```
