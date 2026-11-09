# ADR 0004: Strategy target weights and batch lifecycle

- **Status:** Accepted design contract; target/portfolio implementation and accounting approval remain future gates
- **Date:** 2026-11-09

## Context
An undefined exposure could mean shares, a currency amount, a trade increment, or a desired weight. Omitted and expired targets can likewise mean conflicting actions. These ambiguities must be resolved before strategy and portfolio implementations are joined.

## Decision
Use explicitly labeled signed fractions of positive total account equity as proposed final exposure weights. A strategy publishes a complete replacement batch with unique security IDs, snapshot/version identifiers, and half-open validity `[decision_at, valid_until)`. Omission withdraws that strategy's contribution; it is not permission to cancel another strategy's contribution. Expiry blocks new intents from the expired strategy and requires explicit risk handling of positions/pending orders, without synthesizing liquidation. Invalid batches fail atomically; batch IDs are idempotent only for identical content. A separately versioned portfolio allocation policy combines contributions and applies independent risk constraints.

This chooses proposal units, not a new ledger, settlement, pricing, or sizing convention. Account-equity valuation, FX, rounding, fees, lot sizes, and pending-order conversion still require accounting decisions and independent executable fixtures before implementation. No trading path or target processor is added by this ADR.

## Independent reference specifications for future contract tests
These hand-calculated examples specify intended results; no executable allocator is claimed to exist.

| Case | Inputs | Expected contract outcome |
| --- | --- | --- |
| Final weight, not increment | Equity USD 100,000; target A `equity_weight=0.10`; existing A notional USD 8,000; no pending orders/costs | Desired final notional USD 10,000; unconstrained difference USD 2,000, before later sizing/risk conventions. Repeating the target does not add another USD 10,000. |
| Complete replacement | Strategy S first has A 0.10/B 0.20; replacement has A 0.05 only | S contributes A 0.05 and B zero. Another strategy's B contribution is unaffected. |
| Explicit flat | S's replacement includes A 0 | S contributes zero A; account action still depends on aggregation, state, and risk. |
| Half-open expiry | Decision 14:00, valid until 15:00 | Batch eligible at 14:00 and before 15:00; ineligible at 15:00. No implicit liquidation on expiry. |
| Invalid batch | Duplicate A, NaN weight, unknown units, zero/non-finite equity, or negative weight in long-only mode | Reject before any target/order/account mutation. |
| Replay conflict | Same batch ID with changed weight | Reject conflict; identical content is a no-op. |

## Alternatives
Share targets require security-specific lot/price decisions in strategy code. Currency notionals obscure portfolio scaling. Incremental trades accumulate repeated decisions and create order-lifecycle responsibilities inside strategies. Explicit final weights keep those responsibilities at the portfolio/risk boundary. A future change of units or allocation/accounting policy requires an ADR and independent fixtures.
