# Strategy contract (design draft)

## Purpose
Strategy logic must be independent of where prices come from and whether it runs in historical replay or paper simulation. Broker access is explicitly outside its scope.

## Inputs (future typed interfaces)
- `DecisionContext`: timezone-aware decision timestamp, run ID, data-availability cutoff, mode.
- `ObservationSet`: immutable, as-of-correct prices/features with security IDs and provenance.
- `PortfolioSnapshot`: positions, cash, limits, pending orders, and timestamps.
- `StrategyConfig`: validated immutable parameters and model artifact/version.

## Outputs
A strategy returns a deterministic collection of **proposed target exposures** (not raw broker API commands) with timestamp, security ID, rationale/features, estimate uncertainty, and strategy version. The portfolio engine resolves conflicts, then risk independently approves/rejects order intents.

## Required properties
- No direct network, mutable database, filesystem, or broker calls during strategy evaluation.
- Explicit handling of missing/stale inputs; no silent substitution of future values.
- Identical inputs, code version, and seeded randomness produce identical outputs.
- No assumption that buy and sell orders fill immediately or completely.
- Multiple strategies cannot override account-level risk settings.
- Separate strategies for long-only and short-capable operation; borrowing and fees require explicit modeling.

## Promotion gates
Proposed → backtested → statistically reviewed → untouched holdout → forward paper evaluated → owner-approved limited deployment. A report or agent opinion is never itself an authorization to promote.
