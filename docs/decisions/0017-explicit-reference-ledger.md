# ADR 0017: Explicit-fill reference ledger v1

- **Status:** Proposed; owner approval required before runtime implementation
- **Date:** 2026-11-10

## Context and approval boundary

The first M2 ledger needs an independently specified accounting boundary before
implementation. [ADR 0004](0004-target-exposures.md) accepts target proposal units
and lifecycle, but explicitly leaves ledger, settlement, pricing and sizing
conventions undecided. The
[testing strategy](../testing-strategy.md#pull-request-acceptance)
requires: **"Human approval for financial conventions, dependencies, and any
eventual brokerage access."**

Every choice below is a proposal. The instruction to implement the roadmap does
not approve unspecified financial conventions. This document records no owner
approval, independent-review acceptance, implementation, successful CI or
milestone completion. Approval must identify the exact proposed document revision
and its [reference specification](../m2-reference-ledger-v1.md). No runtime code
implementing these conventions should be written before that approval.

## Proposed bounded scope

A pure deterministic reference ledger would consume explicitly supplied opening
cash, fills and full per-fill settlement events. It would calculate holdings,
settled cash, open trade receivables/payables, available cash and arithmetic
valuation snapshots. All inputs are reference assertions; none are evidence of
actual trades, provider accuracy or historically usable market data.

One opening event would establish zero positions and nonnegative settled cash in
one declared currency. No later funding/withdrawal event is proposed in v1.
The ledger would generate no fills, orders or account instructions. It would
have no network, broker, persistence or filesystem responsibility.

## Five proposed financial decisions

| Decision | Proposed v1 semantics | Material alternative deferred |
| --- | --- | --- |
| Units | Explicitly declare one currency. All money amounts are integer hundredths of that currency; price is integer hundredths per whole share. Quantities are whole shares. Inputs must be exactly representable; reject unsupported precision instead of rounding. | Fractional shares or finer money precision need separate units and rounding decisions. |
| Economic recognition | A buy increases holdings and creates a payable at fill time. A sale decreases holdings and creates a receivable at fill time. Settlement changes cash and clears that obligation, without changing holdings or equity. | Settlement-date holdings would need a different explicit treatment of exposure between fill and settlement. |
| Reservations and sellable shares | Reserve settled cash against every open buy payable. Do not spend unsettled sale proceeds. Shares from an unsettled buy are held but not sellable. Reject insufficient available cash and sales exceeding sellable shares. | Reinvestment of unsettled proceeds or sale of unsettled purchases expands the financing and inventory model. |
| Costs | Every fill declares its nonnegative fee, including explicit zero. Buy payable is gross cost plus fee; sale receivable is gross proceeds minus fee. Recognize the fee's equity effect at fill, with cash movement at settlement. Reject sale fees exceeding gross proceeds. | Immediate cash fee payment, rebates, separate invoices and financing charges need additional conventions/events. |
| Valuation | Require one explicit same-instant valuation assertion for each positive holding. No automatic fill-price mark, carry-forward or missing-price zero. Equity is settled cash plus receivables minus payables plus marked holdings. | Carry-forward marks need explicit freshness, availability and substitution rules. |

The hundredth unit is a reference-model precision choice. It makes no statement
about exchange tick sizes, legally permitted increments, account permissions or
actual settlement practices. Currency identifiers are exact and never converted.
Inputs in any other currency reject.

## Proposed event and valuation contract

The [reference specification](../m2-reference-ledger-v1.md) defines the complete
transition arithmetic and five independently calculated scenarios. In particular:

- Each fill has a unique immutable fill ID as well as its event ID. Separate
  partial fills are separate facts with separately declared prices and fees.
- Settlement occurs only through an explicit event referring to one entire fill.
  Its supplied timestamp must not precede the fill. There is no inferred
  settlement date, calendar, netting or automatic settlement as time advances.
- Input order is explicit, with nondecreasing aware event instants. Equal-time
  events use stream order. Identity compares all declared event fields after
  UTC timestamp normalization; exact IDs/references are never stripped or inferred.
  No event-type priority or automatic sorting is added.
- Identical event-ID retries are no-ops. Conflicting event identities, repeated
  fill IDs, unknown fill references and a second settlement of one fill reject.
- A failed transition leaves the original state intact. Invalid full replay
  returns no successful partial result.
- Valuation is a nonmutating request. Its complete mark set is explicit, with
  nonnegative integer prices at exactly the requested valuation instant. It
  cannot precede the last applied event. It does not advance the event cursor,
  settle obligations or authorize a trade.

The intended accounting invariants are [declared equity, unique fills, explicit
units and deterministic reconciliation](../invariants.md#financial-accounting).
These narrow calculations would not establish all platform financial invariants.
The risk policy still [authorizes no trades](../risk-policy.md).

## Non-goals and remaining gates

No market-data ingestion or historical availability proof; bar/fill simulator;
orders or target conversion; live/paper accounts or broker integration; position
sizing, portfolio allocation or risk engine; FX, fractional shares, financing,
shorts, actions, distributions, taxes, cost-basis lots, realized P&L, strategy
returns/performance or promotion. Corporate actions and adjusted/raw prices need
their own [explicit conventions](../data-contracts.md#corporate-actions); they
are unsupported here, not silently ignored.

No actual source entitlement is assumed: the owner reported none yet. The
reference specification is not a mock provider dataset or an evaluable market
dataset. The implemented
[M1 universe-listing replay](0016-historical-universe-listing-replay.md)
remains an assertion consumer, not an accounting or market-data simulator.
All M1 gates remain open; this proposal closes no M2 gate.

## Approval and future acceptance evidence

Before runtime implementation, record owner identity, date, exact reviewed
revision and explicit acceptance of all five financial decisions, the scope and
reference scenarios. A suitable approval scope is:

> Approve reference-ledger v1 decisions and reference scenarios at revision X
> for implementation within the stated scope.

This is suggested wording for a future decision, not evidence that it occurred.
A changed financial choice requires renewed review of the affected specification
and approval before implementation.

After approval, a separate narrow implementation must have typed immutable APIs,
independent executable reference cases, negative/cross-module invariants,
independent review and actual results for `ruff check .`, `ruff format --check .`,
`mypy src` and `pytest`, plus exact-revision branch CI. No new dependency, storage
system or service is proposed. Prose and local arithmetic alone are not runtime
acceptance evidence.
