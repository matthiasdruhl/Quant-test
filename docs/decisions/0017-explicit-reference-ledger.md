# ADR 0017: Explicit-fill reference ledger v1

- **Status:** Bounded financial conventions accepted; reference scenarios verified
- **Date:** 2026-11-10

## Context and approval boundary

The first M2 ledger needs an independently specified accounting boundary before
implementation. [ADR 0004](0004-target-exposures.md) accepts target proposal units
and lifecycle, but explicitly leaves ledger, settlement, pricing and sizing
conventions undecided. The
[testing strategy](../testing-strategy.md#pull-request-acceptance)
requires: **"Human approval for financial conventions, dependencies, and any
eventual brokerage access."**

The instruction to implement the roadmap did not approve unspecified financial
conventions. The user subsequently approved this bounded v1 proposal and its
[reference specification](../m2-reference-ledger-v1.md) at the exact revision below.
That approval authorizes implementation of those choices; runtime correctness,
independent implementation review, CI and milestone acceptance remain separate.

### Recorded owner approval

- **Approving party:** the repository owner/task user in this Codex conversation;
  no separate external identity verification is claimed.
- **Date and source:** 2026-11-10, the user's reply in this Codex chat to the
  explicit exact-revision approval request. The conversation is the approval
  record; no external review URL is invented.
- **Exact reply:** “Approve v1 as specified”.
- **Approved revision:** `b216d63d3a63c39f8770f6f3500e7e75127da590`.
  Both this ADR and `docs/m2-reference-ledger-v1.md` at that revision are the
  approved baseline, preserved in Git.
- **Scope:** all five financial decisions, the bounded scope and the five
  reference scenarios as specified at that revision. This is no authorization
  for additional financial conventions, simulation assumptions, accounts,
  providers, strategy promotion or orders.

A changed financial choice still requires renewed explicit approval. The
technical API refinement below does not change the accepted arithmetic or scope.

## Accepted bounded scope

The pure deterministic reference ledger consumes explicitly supplied opening
cash, fills and full per-fill settlement events. It calculates holdings,
settled cash, open trade receivables/payables, available cash and arithmetic
valuation snapshots. All inputs are reference assertions; none are evidence of
actual trades, provider accuracy or historically usable market data.

One opening event establishes zero positions and nonnegative settled cash in
one declared currency. No later funding/withdrawal event is supported in v1.
The ledger generates no fills, orders or account instructions. It has no network,
broker, persistence or filesystem responsibility.

## Five accepted financial decisions

| Decision | Accepted v1 semantics | Material alternative deferred |
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

## Accepted event and valuation contract

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
All M1 gates remain open; financial approval alone closes no M2 gate. Separate
[implementation evidence](../m2-reference-ledger-evidence.md) now closes only
M2's reference-ledger scenario gate, with all remaining M2/M3 gates open.

## Technical API refinement for implementation review

`backtest.reference_ledger` adds only immutable in-memory reference facts and
a pure replay/valuation consumer. All constructor arguments are required unless
explicitly described as derived; no implicit zero fee, default currency or default
money unit is introduced:

- `OpeningCashEvent(event_id, occurred_at, reference_id, currency, money_unit,
  settled_cash_hundredths)` requires exact `money_unit="currency_hundredth"`
  and nonnegative opening cash.
- `FillEvent(event_id, occurred_at, reference_id, fill_id, security_id, side,
  quantity_shares, unit_price_hundredths, fee_hundredths, currency)` requires
  exact `side="buy"` or `"sell"`, positive quantity/price and nonnegative fee.
- `SettlementEvent(event_id, occurred_at, reference_id, fill_id)` carries only
  the entire referenced fill's settlement fact, with no replacement amount/fee.
- `ValuationMark(security_id, valued_at, unit_price_hundredths, currency,
  reference_id)` requires a nonnegative explicit price.

Numeric fields require standard `int` values, rejecting bool, integer subclasses,
floats, Decimal and text without coercion. IDs/currency/reference fields require
standard nonblank `str` values, retaining exact text while rejecting subclasses.
The approved standard UTC/fixed-offset/keyed-ZoneInfo real-instant boundary
applies. Event records are frozen and normalize only their timestamps.
`LedgerEvent` is the explicit union of opening/fill/settlement record types.
Only the exact supported event and mark record types are accepted; arbitrary
subclasses and unsupported record kinds reject. Valuation requires an exact
`ReferenceLedger`. This preserves the declared audit/immutability boundary,
without claiming protection against hostile in-process code or deliberate
`object.__setattr__` bypasses.

`ReferenceLedger(events: tuple[LedgerEvent, ...] | list[LedgerEvent])` takes only
an explicit nonempty built-in container, snapshots it and derives every public
balance/position/identity from replay. No cash, position, cursor, obligation,
applied-ID or settled-ID state can be supplied separately. The first distinct
event must be opening cash; only exact retries can repeat it. All new events
preserve nondecreasing UTC order, with equal-time order supplied by the stream.
Global event-ID/full-content equality is checked before time/new-opening/closed-
fill rules, so an old exact retry remains a no-op and retains the first logical
event. Conflicts, duplicate fill IDs, unknown/closed settlements and invalid
transitions reject without registering any new identity or partial success.

The frozen ledger exposes `events` in retained logical input order, `event_ids`
in that order, `settled_fill_ids` and `open_fills` in exact fill-ID order,
`last_event_at`, declared `currency`/`money_unit`, and derived
`settled_cash_hundredths`, `buy_payables_hundredths`,
`sale_receivables_hundredths` and `available_cash_hundredths`.
`positions` is an immutable stable-security-ID ordered tuple of `PositionBalance`
rows containing held/unsettled-buy quantities and computed sellable quantity.
Only positive held positions need rows; original facts remain in `events`.
Position rows are outputs, never accepted as initial ledger state. The replay
maintains `C >= B >= 0`, `R >= 0` and `H[s] >= U[s] >= 0` under the accepted
transition arithmetic. Open fills retain the exact immutable `FillEvent`,
including zero-net sale receivables until explicitly settled.

`ledger.apply(event) -> ReferenceLedger` replays retained events plus the supplied
fact. Exact retries may return the same ledger; failed attempts leave the original
ledger, IDs and cursor unchanged. Full replay never silently skips a rejected
new event. No arrival policy, calendar or automatic settlement is inferred.

`LedgerValuation(ledger, at, marks: tuple[ValuationMark, ...] |
list[ValuationMark])` and `ledger.value_at(at, marks)` require a typed ledger,
real query instant no earlier than its last accepted event and an explicit
built-in mark container. Marks snapshot to stable-security order and must be
exactly the positive holdings, with matching currency and query instant. All
marked amounts/equity are computed only, including
`marked_holdings_hundredths` and `equity_hundredths`; callers cannot inject totals.
Zero holdings require an explicit empty mark set; zero cash/mark/equity remains
valid. A valuation stores no marks in the ledger, registers no event identities
and does not advance its cursor. A later valuation cannot forbid a subsequent
otherwise valid event between the last accepted event and that valuation.

This API section is a technical representation of the approved v1, not a new
financial decision. The five scenarios in the linked reference specification
remain unchanged from the approved baseline. No provider, target conversion, persistence, dependency,
service, fill simulator or trading path is added.

## Runtime acceptance evidence remains separate

Implementation must have typed immutable APIs, independent executable reference
cases, negative/cross-module invariants, independent review and actual results
for `ruff check .`, `ruff format --check .`, `mypy src` and `pytest`, plus the
existing verifier's targeted mypy and exact-revision branch CI. Owner acceptance
of the financial choices does not supply any of those results. Prose and local
arithmetic alone are not runtime acceptance or milestone evidence.

The [dated evidence record](../m2-reference-ledger-evidence.md) supplies those
results for the pushed, unmerged ledger revision and closes only its reference
scenario gate. It does not extend the financial approval or complete M2.
