# ADR 0018: Immutable long-only target batches and lifecycle selection

- **Status:** Proposed technical refinement; implementation under review
- **Date:** 2026-11-10

## Context and bounded scope

[ADR 0004](0004-target-exposures.md) accepts explicitly labeled equity fractions,
complete replacement per strategy and half-open expiry. It reserves allocation,
valuation, sizing and accounting decisions. The broader
[strategy contract](../strategy-contract.md) describes signed target proposals
and future complete strategy outputs. This slice implements only their explicitly long-only quantity and lifecycle
subset in `strategies.targets`. It does not replace the general signed design
or implement a strategy runner.

This ADR refines typed representation, caller-context correspondence and pure
history selection. It adopts no financial conversion, accounting, allocation or
risk convention. The [M2 ledger proposal](0017-explicit-reference-ledger.md)
remains separately Proposed and requires explicit owner approval before runtime
implementation. All milestone gates remain open.

## Immutable APIs

All records are frozen. IDs are required exact nonblank text, including run,
strategy, strategy version, batch, stable security and snapshot IDs. Whitespace,
case and punctuation remain part of identity; IDs are not stripped, resolved as
tickers or treated as authenticated checksums.

- `TargetProposal(security_id: str, unit: str, equity_weight: Decimal)` requires
  every argument, including the exact unit `"equity_weight"`. Weight must be a
  standard finite, nonnegative `Decimal`; bool, int, float, text and unsupported
  numeric/subclass values reject without coercion. Explicit zero is valid,
  including numerically equal signed zero. Values are fractions, not percentages:
  `Decimal("10")` remains ten fractions, never silently divided by 100. There is
  no per-target ceiling, sum limit, cash/position conversion or permission to hold
  that exposure. Numeric validation does not enforce portfolio limits.
- `TargetSnapshotAssertion(snapshot_id: str, as_of_at: datetime,
  asserted_usable_at: datetime)` retains two distinct caller-asserted instants.
  A snapshot ID is not its contents or a verified archive reference. This record
  alone imposes no decision-relative eligibility or freshness rule.
- `TargetBatch(run_id: str, strategy_id: str, strategy_version: str,
  batch_id: str, decision_at: datetime, valid_until: datetime,
  data_cutoff_at: datetime, data_snapshot: TargetSnapshotAssertion,
  portfolio_snapshot: TargetSnapshotAssertion, targets: tuple[TargetProposal,
  ...] | list[TargetProposal])` requires all fields. Its explicit built-in tuple
  or list input is snapshotted into an immutable tuple, sorted by exact security
  ID; duplicate security IDs reject, even for identical proposals. Generators,
  mappings, strings, sets, mutable/untyped entries and container subclasses reject.
  Explicit empty tuple/list is a valid complete replacement.
- `TargetDecisionContext(run_id: str, strategy_id: str, strategy_version: str,
  decision_at: datetime, data_cutoff_at: datetime,
  data_snapshot: TargetSnapshotAssertion,
  portfolio_snapshot: TargetSnapshotAssertion)` pins the expected caller context.
  It contains no batch ID, expiry or targets and requires the same identity/time/
  snapshot consistency checks as the corresponding batch fields.
- `validate_target_batch_for_context(batch: TargetBatch,
  context: TargetDecisionContext, at: datetime) -> None` raises `ValueError` for
  invalid types or any mismatch. Success returns normally without mutation. All
  shared stream, version, decision, cutoff and full snapshot assertions must match;
  matching snapshot IDs alone is insufficient. The query instant must fall in
  the batch's `[decision_at, valid_until)` window.

`Decimal` values retain exact numeric meaning without arithmetic normalization,
rounding or dependence on the ambient decimal precision for validation. Numeric
value equality applies: `Decimal("0.10") == Decimal("0.1")`. Their exponent,
spelling and signed zero are not different target identities. No canonical byte
encoding or persistence representation is introduced.

## Time and assertion consistency

All time fields and query instants require standard real aware `datetime`
values. Supported zones are UTC, standard fixed-offset `timezone` and reopenable
keyed `ZoneInfo`; a key must reproduce the supplied instant's offset and name.
Reject naive/date/datetime-subclass/unsupported-zone values, nonexistent civil
times and out-of-range UTC conversions as `ValueError`. Check civil roundtrips
before normalization, preserving distinct valid folds. Normalize stored/query
instants to UTC with `fold=0`. Equivalent offsets compare by instant rather than
original representation. This follows the narrow validation rule in
[ADR 0016](0016-historical-universe-listing-replay.md) without changing existing
in-memory time or data query APIs.

Batches require `data_cutoff_at <= decision_at < valid_until`. Contexts require
`data_cutoff_at <= decision_at`. In either:

- Data snapshot `as_of_at` equals `data_cutoff_at` by UTC instant.
- Portfolio snapshot `as_of_at <= decision_at`.
- Both snapshots have `asserted_usable_at <= decision_at`, including equality.

There is no guessed maximum age or additional ordering between snapshot as-of
and asserted-usability instants. These checks compare the specified assertions;
they do not establish the actual contents, coverage, source availability,
processing completion or temporal validity of either snapshot. A caller can
assert matching but false metadata. The expected context is itself a caller
assertion, not authenticated platform state or a current portfolio check.

## Complete history, identity and selection

`TargetBatchHistory(run_id: str, strategy_id: str, strategy_version: str,
batches: tuple[TargetBatch, ...] | list[TargetBatch])` is frozen and takes only
explicit built-in tuple/list inputs, including empty. It snapshots all typed
batches, validates the entire collection before any query filtering and stores
the distinct batches sorted by decision instant. Every batch must belong to the
exact pinned run/strategy/version stream; mixed streams or versions reject rather
than being silently excluded. Independent streams use separate histories.

Batch ID scope is that full pinned stream. A retry with the same ID and identical
normalized batch content is a no-op: it adds no decision and does not replace the
retained batch or snapshot assertions. Equality includes every declared field,
UTC instants, exact text, sorted targets and Decimal numeric values. Changed
content under that ID rejects. Distinct IDs at the same UTC decision instant
reject, even with identical proposals: arrival order, lexical IDs and expiry
cannot choose a winner. Future/expired/unselected conflicts also reject globally.

Within each snapshot role separately, reuse of a snapshot ID requires identical
normalized `(as_of_at, asserted_usable_at)` metadata throughout the history.
Changed metadata rejects even when both batches independently pass their own
context checks. Data and portfolio roles have separate ID namespaces; equality
of a data ID and a portfolio ID does not merge the roles or imply common contents.
This is assertion consistency, not content-address validation or a snapshot store.

`history.selected_at(at: datetime) -> TargetBatchSelection` returns a frozen
selection containing the exact stream IDs, normalized query instant and selected
batch (or `None`). Its `status: TargetBatchStatus` and
`active_targets: tuple[TargetProposal, ...]` are computed outputs, never trusted
caller reports. Status has exactly `NO_BATCH`, `ACTIVE` and `EXPIRED`:

1. Select the latest batch with `decision_at <= at` before testing expiry.
2. With no such batch, retain `selected_batch=None`, status `NO_BATCH`, and no
   active targets.
3. With a batch and `at < valid_until`, retain that batch, status `ACTIVE`, and its
   complete ordered target tuple. Active empty targets remain distinguishable
   through the status and selected batch.
4. Otherwise retain the latest batch as expired provenance, status `EXPIRED`,
   and no active targets. Never fall back to an older still-unexpired batch.

The immutable history retains all supplied distinct batch assertions. Selection
does not query current account state and describes lifecycle eligibility only.
Context validation is a separate explicit check; selecting a batch is not proof
that it matches any caller's expected snapshots or decision context.

Public direct `TargetBatchSelection(run_id, strategy_id, strategy_version, at,
selected_batch)` construction validates exact nonblank stream IDs, the real query
instant and selected-batch type/stream, and requires its decision no later than
the query. `status` and `active_targets` are derived only, not constructor inputs.
Direct construction cannot establish that the supplied batch is latest in any
history; only `history.selected_at` performs the complete-history selection.

Historical selection queries the asserted decision timeline, not actual batch
arrival, publication or operational receipt. No arrival timestamp/policy is
inferred. A historically active assertion does not prove an actual consumer had
received it at that instant or authorize operational use.

A replacement's omission of a security withdraws only this stream's contribution;
it does not synthesize a zero proposal, cancel another stream, create an order or
liquidate a holding. Explicit zero remains an actual proposal. Expiry produces no
new eligible proposal or automatic liquidation and does not prescribe future risk
handling of holdings or pending orders.

## Independent reference acceptance cases

These hand-specified cases concern quantities and lifecycle, not position sizing,
account-equity arithmetic, investment recommendations or strategy performance.
All timestamps in the table are explicit UTC instants on one fixture date;
weights are supplied as `Decimal` values with the required unit.

| Case | Explicit assertions | Required result |
| --- | --- | --- |
| Complete replacement | Stream S batch b1 at 14:00, expiry 18:00: A .10, B .20. S batch b2 at 15:00, expiry 17:00: A .05 only. | At 14:00 select b1; at 15:00 select b2 with only A .05. B is omitted from S, not inherited or emitted as a synthetic zero. |
| Stream isolation | Separate stream T has B .30 active across S's replacement. | T's separate history still returns B .30; S never changes it. Mixed S/T or version/run records in one pinned history reject. |
| Explicit zero and empty | S batch b3 explicitly proposes A 0; later b4 has an explicit empty target tuple. | Both are ACTIVE within their windows; b3 returns A 0, b4 returns no targets with selected b4. Neither means NO_BATCH or authorizes an account action. |
| Half-open expiry and no fallback | S b1 at 14:00 expires 18:00; newer b2 at 15:00 expires 16:00. | At 15:00 b2 is ACTIVE; immediately before 16:00 still ACTIVE; at 16:00 b2 is EXPIRED with no active targets despite b1's later expiry. |
| Future decisions | All batches decide at or after 14:00; query 13:59:59.999999. | NO_BATCH with no selected batch or active targets. No future decision leaks into selection. |
| Retry normalization | Repeat b1 with equivalent UTC instants, target input order reversed and .100 instead of .10. | One retained logical batch; retry changes neither history length nor retained assertions. Changing weight, unit, expiry, stream or any snapshot assertion under that ID rejects. |
| Global conflicts and ties | Include an unselected future duplicate-ID conflict, different IDs at one decision instant, or reused snapshot ID with changed metadata. | History construction rejects before any selection, regardless of input permutation or the query cutoff. |
| Snapshot/context boundary | Data as-of equals cutoff; cutoff and both asserted usable instants equal decision; portfolio as-of equals decision. | Valid assertions. Changing any expected stream/decision/cutoff/full-snapshot field rejects context validation; any later asserted-usability/portfolio-as-of or mismatched data-as-of rejects construction. |
| Exact quantities and types | Required unit omitted/unknown; negative/non-finite Decimal; bool/int/float/text weight; duplicate IDs or implicit target containers. Separately supply finite Decimal 10 or zero. | Invalid assertions reject without coercion/partial mutation. Decimal 10 remains ten fractions; zero remains zero, with no exposure permission or sum/ceiling enforcement. |
| Immutability and real instants | Mutate source lists after construction; use equivalent offsets, both valid folds, gaps, naive/date/subclass/custom-zone values or UTC overflow. | Stored tuples remain unchanged; equivalent instants match, folds stay distinct, and invalid scalar/civil assertions reject. |

## Trust boundary, non-goals and future evidence

Snapshot assertions do not prove raw receipt admission, actual source/operational
availability, recursive derived/model lineage, data quality, content identity,
current portfolio or freshness. No guessed age threshold or authenticated
snapshot resolver is added. No network, filesystem, mutable database, broker,
new dependency or service is needed.

Rationale, features, forecasts, uncertainty and a complete runnable strategy
output remain future work. There is no ledger/valuation/price/FX/share/rounding/
fee conversion, sizing, allocation, gross/net limits, aggregation, order intent,
risk approval, broker/execution, persistence, experiment registry or holdout
handling. This technical boundary does not adopt the M2 financial proposal or
close M1/M3 gates. LLM proposals remain untrusted hypotheses, never orders.

The narrow typed implementation has independent executable quantity/lifecycle
references and negative cases; broader design contracts remain future work.
Acceptance requires the repository's four mandatory checks, local link/fragment
and diff checks, independent review and exact-revision branch CI. This ADR records
no remote CI success, owner financial acceptance or milestone approval.
