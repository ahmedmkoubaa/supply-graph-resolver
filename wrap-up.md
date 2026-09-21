# Part 4: Wrap-Up & Next Steps

### 1. What to instrument or test before this ships
* **Human-in-the-Loop Feedback Loop:** Before treating the confidence scores as authoritative, we must instrument a UI mechanism for anchor companies to explicitly "Accept" or "Reject" our Tier-2 inferences. This generates the ground-truth labeled data required to tune our initial V1 heuristic weights (Recency, Frequency, Volume) into a calibrated model.
* **Precision vs. Recall Baselining:** Before exposing this to all clients, I would run the pipeline against a small subset of heavily researched, known supply chains (e.g., a specific aluminum or chemicals vertical). This allows us to establish a baseline for our false-positive and false-negative rates in the wild.

### 2. What to explicitly punt to Version 2
* **Dynamic Corporate Registry Integration:** The V1 hardcoded Alias/Exclusion dictionaries prove the concept, but do not scale. V2 will punt this to an external enterprise API (such as Dun & Bradstreet, OpenCorporates, or EcoVadis's internal entity resolution service) to programmatically resolve parent/subsidiary relationships and legal renames.
* **Multi-Modal and Multi-Region Coverage:** V1 is strictly limited to US inbound ocean freight. Integrating air freight, cross-border trucking, and EU/Asia customs feeds introduces massive schema variations, distinct regional broker behaviors, and varying data reliability. Expanding the pipeline to handle these global modalities is strictly deferred to V2.