# Part 1: Trade-Off Memo — Customs Data as a Tier-N Signal

## Overview
Tier-1 data is reliable because both sides confirm it — but it stops at the first hop, exactly where sustainability and concentration risk usually hides. Customs bill-of-lading data is the only signal that reaches past Tier 1 without anyone self-reporting, and the raw data itself is public and free.

---

## 1. What It Costs (The Three Deficits)

Customs bill-of-lading trade feeds come with three fundamental trade-offs:

1. **Coverage (Structural Blind Spots):**
   - Covers **only** international ocean freight landing in the US.
   - Suppliers reached by air, truck, rail, or sold domestically never appear — a structural blind spot that data cleaning cannot fix.

2. **Noise (Data Artifacts):**
   - Corporate renames, intra-group shipments disguised as new supplier links, coincidental name collisions, and freight-forwarder pass-throughs.
   - The intra-group pattern is not a static one-time filter; it is an evolving heuristic that requires continuous tuning.

3. **Confidence (Compounding Uncertainty):**
   - Nothing in ocean manifests is verified or confirmed by either counterparty.
   - Uncertainty compounds exponentially with every hop. Beyond name/ID matching, shipment metadata (volume, frequency, and recency) must be weighted to establish edge confidence.

---

## 2. Free vs. Paid (Build vs. Buy)

The decision between a free raw feed and a paid trade API (e.g. Panjiva, ImportGenius) is fundamentally a **build-vs-buy** strategic decision:

- **Free Raw Feed:** The raw feed costs nothing up front, but resolving noisy names into defensible buyer-facing signals incurs **ongoing engineering costs indefinitely** as corporate structures evolve.
- **Paid Vendor Feed:** A paid API purchases third-party entity resolution and broader multi-modal transport coverage (air, rail, regional) — not just "cleaner data" — at the expense of internal tunability.

### Strategic Recommendation
> **Phase 1 (Validate Market Demand):** Use the free customs feed now to build a working prototype and prove that buyers actually value a Tier-N discovery feature.  
> **Phase 2 (Scale Coverage):** Revisit a paid vendor specifically to close the modal coverage gap (air/land freight) once demand is proven. *Note: A paid vendor fixes coverage, not entity confidence decay.*

---

## 3. Product & Rollout Strategy

Because Tier-N trade data can never be fully verified against ground truth:
- **Phase Rollout:** Ship from a small, manually checked slice of high-volume suppliers first.
- **Display Confidence Bands:** Present confidence scores as range bands rather than binary yes/no assertions.
- **Continuous Recalibration:** Treat confidence scoring as a dynamic heuristic tuned by human-in-the-loop feedback over time.
