# Phase 41 — Real A-share Data Workbench

## Goal

Connect the certified historical market files and a point-in-time (PIT) universe
into an incremental, memory-bounded factor dataset suitable for empirical testing.

## Hard boundaries

- The workbench never substitutes today's stock list for history.
- Listing/delisting dates alone do not establish historical ST, suspension, or
  corporate-action eligibility; those require separate PIT sources.
- Certified CSVs remain SHA-256 verified inputs.
- Factors are computed only from bars available on or before the observation date.
- No synthetic factor fill is allowed.
- A successful workbench run is **not** an Alpha claim. Final evidence still requires
  factor validation, Walk-Forward/OOS, transaction costs, benchmark alignment and
  A-share execution constraints.

## 8GB design

Each stock is processed one at a time and factor rows are streamed to JSONL. The
pipeline avoids loading a full market-by-day matrix into RAM.

## Recommended real-data order

1. Acquire/freeze historical daily bars with adjustment convention explicitly recorded.
2. Build a PIT security master and daily/periodic universe snapshots.
3. Add historical ST/suspension/delist/corporate-action constraints.
4. Run this workbench to create factor rows.
5. Run `factor_lab.py` and then Walk-Forward/OOS.


## Phase 43
Real daily-file adapter and price-factor reconnaissance were added. This remains reconnaissance only until PIT security master, corporate actions, ST/suspension, costs and OOS validation are supplied.
