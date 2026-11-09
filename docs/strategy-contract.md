# Strategy contract (design draft)

## Purpose
Strategy logic must be independent of where prices come from and whether it runs in historical replay or paper simulation. Broker access is explicitly outside its scope.

## Inputs (future typed interfaces)
- `DecisionContext`: timezone-aware decision timestamp, run ID, data-availability cutoff no later than decision time, mode, and next scheduled decision/target expiry.
- `ObservationSet`: immutable, as-of-correct prices/features with security IDs and provenance.
- `PortfolioSnapshot`: positions, cash, limits, pending orders, and timestamps.
- `StrategyConfig`: validated immutable parameters and model artifact/version.

## Outputs
A strategy returns a deterministic collection of **proposed target exposures** (not raw broker API commands) with timestamp, security ID, rationale/features, estimate uncertainty, and strategy version. The portfolio engine resolves conflicts, then risk independently approves/rejects order intents.

### Target semantics (design only)
The initial proposal unit is a signed, dimensionless **fraction of total account equity**: `0.10` means a desired position worth 10% of equity in the account's declared base currency; `0` explicitly requests a flat position. These are desired final positions, not trade increments. A target must declare `unit="equity_weight"`; shares, percentages expressed as `10`, and currency notionals cannot be accepted as interchangeable units. Equity must be finite and positive before conversion. Long-only targets must be nonnegative; gross/net limits are independently enforced rather than inferred from a model's confidence.

Each immutable batch contains strategy/run/batch IDs, the decision and snapshot IDs, `valid_until`, and at most one target per security ID. Require `decision_at < valid_until`; a batch is effective on `[decision_at, valid_until)`. It is a complete replacement of that strategy's previous targets. Omission explicitly withdraws that strategy's allocation for that security, equivalent to zero contribution; it does not cancel another strategy's allocation or directly liquidate the account. Between batches, targets persist only until expiry. At expiry without a valid replacement, block new order intents for the affected strategy and require explicit risk handling of existing positions and pending orders; expiry itself never synthesizes a liquidation or leaves an old target eligible for new orders.

Reject duplicate security IDs, unknown units, non-finite weights, stale/inconsistent snapshots, expired/future batches, and invalid IDs without partial mutation. Replayed batch IDs are idempotent only when content is identical; conflicting contents with the same ID are rejected. Multiple strategies' weights are combined by a versioned allocation policy with account limits applied afterward. There is no implicit winner based on iteration order.

The portfolio layer converts weights using the explicitly identified equity/price/FX snapshot, then considers existing positions and pending orders. Fractional-share support, lot rounding, cash/settlement, costs, and sizing conventions require accounting reference fixtures before implementation; no rounding default is introduced here. See [ADR 0004](decisions/0004-target-exposures.md) for independent design examples. No target, allocator, or order interface is implemented yet.

## Required properties
- No direct network, mutable database, filesystem, or broker calls during strategy evaluation.
- Explicit handling of missing/stale inputs; no silent substitution of future values.
- Identical inputs, code version, and seeded randomness produce identical outputs.
- No assumption that buy and sell orders fill immediately or completely.
- Multiple strategies cannot override account-level risk settings.
- Separate strategies for long-only and short-capable operation; borrowing and fees require explicit modeling.

## Promotion gates
Proposed → backtested → statistically reviewed → untouched holdout → forward paper evaluated → owner-approved limited deployment. A report or agent opinion is never itself an authorization to promote.

The [research protocol](research-protocol.md) defines registration, consumed holdouts, and failed attempts. An owner/reviewer must approve each stage's recorded evidence; agents cannot promote a strategy automatically. Historical artifacts must meet [derived availability rules](data-contracts.md#derived-features-and-model-artifacts) before backtest results are eligible evidence.
