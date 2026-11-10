# Explicit-fill reference ledger v1: approved reference specification

- **Status:** Bounded v1 conventions approved; runtime verification separate
- **Date:** 2026-11-10

This is the human-readable specification accompanying
[ADR 0017](decisions/0017-explicit-reference-ledger.md). The repository owner/task
user approved its bounded v1 conventions, scope and five reference scenarios in
this Codex chat on 2026-11-10 with the exact reply “Approve v1 as specified”, in
response to the exact-revision approval request for
`b216d63d3a63c39f8770f6f3500e7e75127da590`. The complete
[approval record](decisions/0017-explicit-reference-ledger.md#recorded-owner-approval)
distinguishes that financial decision from runtime/CI/milestone acceptance.

The [testing strategy](testing-strategy.md#pull-request-acceptance) requires human
approval for financial conventions. That requirement is satisfied only for this
identified baseline, not additional conventions or any brokerage/trading path.
The arithmetic/reference scenarios below remain unchanged from that revision;
the ADR's technical API refinement adds no financial choice.

## Input and arithmetic boundary

Declare one exact currency identifier and explicitly declare that money is
measured in integer hundredths of that currency. A unit price is hundredths per
whole share. This bounded model supports no other precision, no rounding and no
FX. Currency and its hundredth unit must be supplied explicitly at opening;
there is no default currency or precision. Every money-bearing input must use
that declared currency. Example USD notation below is solely a human-readable
rendering of integer hundredths.

Quantities are positive integers for fills. Fill prices are positive integers;
fees are nonnegative integers and must always be supplied, including zero.
Valuation prices are nonnegative integers; a caller may explicitly assert zero.
Booleans, floating-point values, fractional quantities, negative fees and
unsupported units reject. The positive integer fill quantity is a share count,
not a signed quantity; the explicit side determines direction. Stable security
IDs are exact identifiers, not tickers. Currency, event/fill/security IDs and
reference identifiers must be nonblank text and retain exact case, punctuation
and whitespace; they are never stripped, case-folded or converted.

Every event has a nonblank event ID, aware event timestamp and nonblank reference
identifier retained with the event. Fill events additionally have a nonblank
fill ID, security ID, side exactly `buy` or `sell`, quantity, price, fee and
currency. Settlement events refer to one fill ID and declare no replacement
quantity, price, amount or fee; the full obligation comes from that exact fill.
Reference identifiers are caller assertions, not authenticated source provenance.
There are no source/publication/ingestion times
to infer: these inputs are explicit accounting reference facts, not external
market observations.

One opening-cash event must be first. It declares nonnegative settled cash and
zero positions; it cannot recur under a new event ID. Later deposits,
withdrawals, corrections and cancellation events are unsupported. Unsupported
event types reject rather than being ignored.

Event and valuation instants require standard aware datetimes with UTC, standard
fixed offsets or reopenable keyed ZoneInfo reproducing the offset/name, as at the
[existing replay boundary](decisions/0016-historical-universe-listing-replay.md).
Reject naive/date/subclass/unsupported-zone values, nonexistent civil times and
UTC overflow. Normalize to UTC with fold zero; valid folds remain different
instants. This is approved input validation; runtime verification is a separate gate.
Events are supplied in explicit nondecreasing time order. Equal-time events use
their input order, without
automatic sorting or settlement-first priority. Settlement must not precede its
fill. There is no calculated due date or calendar. A missing settlement event
leaves the obligation open; advancing time does not settle it or prove the stream
complete.

## State and approved transitions

Let `C` be settled cash in hundredths; `B` the sum of open buy payables; `R` the
sum of open sell receivables; `H[s]` held shares of security `s`; and `U[s]` the
sum of quantities in that security's open buy fills. Each open obligation retains
the identity and exact contents of its fill.

- Available cash is `C - B`. It must never be negative.
- Sellable shares of `s` are `H[s] - U[s]`. They must never be negative.
- Buy gross is `quantity * price`. Buy obligation is `gross + fee`. Accept only
  if that obligation is no greater than available cash. On acceptance increase
  `H[s]`, `U[s]` and `B` by the fill's quantity/obligation. Do not move `C` yet.
- Sell gross is `quantity * price`. Reject quantity above sellable shares or fee
  above gross. On acceptance decrease `H[s]` and increase `R` by `gross - fee`.
  Do not move `C` yet. A zero net receivable is an explicit permitted obligation.
- A buy settlement decreases `C` and `B` by that fill's entire obligation and
  decreases `U[s]` by its quantity. It leaves `H[s]` unchanged.
- A sale settlement increases `C` and decreases `R` by that fill's entire net
  receivable. It leaves holdings unchanged, including for zero net receivables.
- Every settlement closes exactly one fill. No partial settlement or cross-fill
  netting is supported. Separate partial fills require separate IDs and fees.

Each event ID is global within one replay, including across event types. Event
identity compares the entire declared event: type, event ID, UTC-normalized
instant, reference ID and every applicable opening/fill/settlement field.
Equivalent offsets representing one real instant therefore compare identically;
different valid folds do not. Exact text remains part of identity. Identical
content under an existing event ID is a no-op, even when retried after later
events; perform this identity check before applying monotone-time validation to
a new event. A retry does not advance or rewind the last accepted event instant.
Changed content under an existing event ID rejects. A fill ID cannot recur under
a different
event ID, even with identical economic fields. A settlement with an unknown fill
or an already settled fill rejects. An identical settlement-event retry is still
a no-op because it is the same previously applied event.

Validate a transition completely before accepting it. Rejection preserves all
previous state, last accepted event instant and applied-event/fill identities;
rejected IDs are not consumed. A full replay containing any rejected new event
fails and returns no successful partial state. A caller may separately attempt
a corrected transition from the last valid immutable state, but must not silently
skip failed events and call that original full replay successful. This specifies
immutable transition behavior; it does not prescribe a durable storage or
transaction system.

## Approved valuation requests

A valuation request is nonmutating. Its timestamp must be aware, valid and no
earlier than the last accepted event. Supply exactly one valuation assertion for
every security with positive held quantity, and no others. An assertion contains
security ID, explicit price/currency, the exact same valuation instant and a
nonblank retained reference identifier. With no holdings, the required set is
explicitly empty. Missing, duplicate, extra, future-dated or differently timed
marks reject the request; no price is inferred or carried forward. Same instant
means equality after the UTC normalization above. A request and its marks do not
register accounting event IDs or advance the accepted-event cursor. A later
valuation alone therefore does not prohibit an otherwise valid subsequent event
whose instant is between the last accepted event and that valuation.

For explicitly supplied `P[s]`, equity in hundredths is:

`E = C + R - B + sum(H[s] * P[s])`

Settlement changes only the decomposition of cash/obligations, so it leaves `E`
unchanged for unchanged holdings and valuation inputs. The fee reduces equity
when the fill is recognized, although cash moves at settlement. No realized P&L,
tax-lot or return series is produced. These valuations are arithmetic assertions,
not proven historically available observations or strategy performance evidence.

## Independently hand-calculated reference scenarios

All amounts below use an explicitly declared USD currency and integer hundredths.
Amounts displayed with a dollar sign are explanatory only. Every fill declares
its fee. Events use distinct IDs except the intentional replay/conflict cases.
Use `2025-01-02T09:00:00Z` as opening time, `10:00:00Z` for the first fill and
`11:00:00Z` for its explicit settlement unless a scenario states another order.
These are chosen fixture instants, not exchange-session or settlement-calendar
claims. `A` below is the exact stable security ID `A`, not a ticker inference.
All other identifiers are explicit fixture assertions under this convention:

| Event role | Event ID | Fill reference | Reference ID |
| --- | --- | --- | --- |
| Opening in independent scenario `sN` | `sN/open` | none | `reference/sN/open` |
| Fill `F` in scenario `sN` | `sN/fill/F` | exact fill ID `F` | `reference/sN/fill/F` |
| Settlement of `F` in scenario `sN` | `sN/settle/F` | exact fill ID `F` | `reference/sN/settle/F` |

Here `sN` expands to the literal `s1`, `s2`, `s3`, `s4` or `s5`, and `F` to the
stated fill ID (for example `s1/fill/B1`). Scenarios 2 and 4 reuse scenario 1's
accepted prefix and its original IDs; scenario 2's new events use `s2`. Each
intentional conflicting retry changes only its stated fields; a new conflicting
settlement uses a distinct event/reference ID. No other IDs are inferred at
runtime. Each valuation request supplies fresh explicit marks at its exact
instant, with reference `valuation/sN/T/label`, where `T` is that UTC instant and
`label` distinguishes alternative requests. Reference names carry no authenticity
claim. Rejection examples are separate attempted transitions from the stated
valid prefix; they are not silently skipped in a purported successful full replay.

### 1. Buy, fee recognition and full settlement

Open cash $1,000. Buy fill `B1`: 10 A at $20, fee $1.

- Gross = `10 * 2000 = 20000`; payable = `20000 + 100 = 20100`.
- Before settlement: `C=100000`, `B=20100`, `R=0`, `H[A]=10`, `U[A]=10`.
  Available cash is `79900` ($799); sellable A is zero.
- At January 2 10:30, explicit mark $20 gives
  `E=100000-20100+10*2000=99900` ($999).
- A separate nonmutating request at 10:30 with explicit mark $22 gives
  `E=100000-20100+10*2200=101900` ($1,019).
- Settle `B1` explicitly at 11:00. Now `C=79900`, `B=0`, `U[A]=0`, holdings 10
  and sellable 10. Fresh requests/marks at 11:00 at the respective $20/$22 prices
  still give $999/$1,019; the earlier 10:30 marks are not carried forward.

### 2. Distinct partial fills, separate costs and settlements

Start from scenario 1 after settlement. On January 2 at 12:00 sell fill `S1`:
4 A at $25, fee $0.50. At 12:01 sell distinct fill `S2`: 2 A at $24, fee $0.25.
Value the remaining shares explicitly at $24 at 12:02.

- `S1` receivable = `4*2500-50=9950` ($99.50).
- `S2` receivable = `2*2400-25=4775` ($47.75).
- Holdings = `10-4-2=4`; `C=79900`, `B=0`, `R=14725`, `U[A]=0`.
- Marked holdings = `4*2400=9600`; equity = `79900+14725+9600=104225`
  ($1,042.25). Available cash remains $799 before either sale settles.
- Explicitly settle `S1` on January 3 at 11:00: `C=89850`, `R=4775`.
  A fresh 11:00 request with explicit same-instant $24 mark gives
  `89850+4775+9600=104225`.
- Settle `S2` at 11:01: `C=94625`, `R=0`. A fresh 11:01 request with explicit
  same-instant $24 mark gives `94625+9600=104225`.

### 3. Cash reservation and unsettled-share rejection

Open $100. Buy `B1`: 6 A at $10, fee $1. At 10:01 attempt `B2-bad`: 4 A at
$10, fee $0; then at 10:02 submit distinct `B2`: 3 A at $10, fee $0.

- `B1` payable = `6*1000+100=6100`; available cash = `10000-6100=3900`.
- `B2-bad` needs `4000`, more than `3900`: reject with the prior state unchanged.
  Its event/fill IDs are not registered as accepted events.
- `B2` needs `3000`, so accept: `C=10000`, `B=9100`, holdings 9, unsettled buys 9,
  available cash `900` ($9), sellable zero. An attempted sale before settlement
  rejects. At 10:03 with an explicit same-instant $10 mark, equity is
  `10000-9100+9000=9900` ($99).
- Settle `B1` at 11:00: `C=3900`, `B=3000`, holdings 9, unsettled buys 3,
  available cash `900`, sellable 6. Sale of 7 shares rejects, although holdings
  are 9. A fresh 11:00 request with explicit same-instant $10 mark gives
  `3900-3000+9000=9900`.

### 4. Event identity and settlement conflicts

Start from scenario 1 after settlement: `C=79900`, `B=R=0`, holdings/sellable A
both 10. Retry the exact `B1` event and exact settlement event, preserving their
original IDs, references and timestamps. Both are no-ops, despite occurring after
the replay cursor advanced to January 2 11:00. A nonmutating request at 11:01
with explicit same-instant $20 mark gives `79900+10*2000=99900`.

Each of the following independently rejects and preserves that same state:

- Original buy event ID with price changed from $20 to $21.
- A new event ID reusing fill ID `B1`, even with unchanged economic details.
- A new settlement event ID referring to the already settled `B1`.
- Settlement referring to an unknown fill ID.

### 5. Equal-time event order and invalid valuation requests

Open $100. At 10:00 buy `B1`: 2 A at $10, fee $0. State is `C=10000`, `B=2000`,
holdings 2, unsettled buys 2, sellable zero.

- At 11:00 try to sell 1 A at $12, fee $0, before applying buy settlement:
  reject, retaining the above state.
- In a separate valid sequence at that same instant, first settle `B1`, then
  apply the sale with distinct fill/event identities. State is `C=8000`, `B=0`,
  `R=1200`, holdings/sellable A both 1. Explicit $12 mark at 11:00 gives
  `E=8000+1200+1200=10400` ($104).
- In separate requests at 11:00, explicit same-instant $12 marks give
  `10000-2000+2*1200=10400` before buy settlement and `8000+2*1200=10400`
  after buy settlement but before the sale. Settlement changes no equity; the
  subsequent zero-fee sale at that same mark also leaves equity unchanged.
- From the valid post-sale state, a valuation with no A mark rejects. A request
  at 11:00 whose A mark is valued at 11:00:01 rejects. Neither request mutates
  state or registers a new accounting event.

## Runtime acceptance and exclusions

These expected values were specified before runtime implementation. Independent
executable cases verify each state transition, settlement neutrality, reservations,
idempotence and exact rejection state.
Additional negative cases must cover units/types, currency mismatch, fees,
short-sale attempts, settlement before execution, timestamp gaps/folds,
out-of-order new events, unsupported event kinds and invalid mark sets.

Runtime acceptance requires the repository's
[change procedure](../AGENTS.md#change-procedure),
four required checks, exact-revision CI and independent review in addition to
the recorded exact-revision approval. This specification does not itself implement
a simulator, source validator, experiment runner or any trade-authorizing path.
It chooses no corporate-action, tax-lot, realized-P&L, financing or
strategy-performance convention. It closes no
M1 or M2 milestone gate; see the [roadmap](roadmap.md).
