# Phase 38 — A-share Candidate Factor Pool & Evidence Gate

## Goal
Expand the factor search space without blindly stacking correlated signals.
The registry contains 24 candidates across momentum, risk, liquidity,
valuation, quality, growth and A-share-specific event/positioning groups.

## Rules
- Only factors with real point-in-time inputs are eligible for validation.
- Missing sources are reported as `missing_source`; no synthetic values.
- Lightweight validation uses the existing leakage-aware `factor_validation`.
- The gate is a **pre-screen**, not proof of Alpha.
- Redundant passing factors with absolute Pearson correlation >= 0.80 are
  pruned, keeping the stronger RankICIR/RankIC candidate.
- Final acceptance still requires chronological Walk-Forward, untouched OOS,
  A-share trading constraints, realistic costs and benchmark comparison.

## Current implementation
`factor_registry.py` defines candidate metadata and availability checks.
`factor_gate.py` provides quality thresholds plus redundancy pruning.

Technical/bar factors can be tested now when supplied by the bar/factor layer;
PIT fundamentals and A-share event factors remain explicitly source-gated.

## Important boundary
A synthetic or current snapshot cannot establish real A-share Alpha. This
phase only improves the research machinery and makes factor admission more
systematic.
