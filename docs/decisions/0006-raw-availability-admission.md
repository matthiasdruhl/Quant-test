# ADR 0006: In-memory raw availability admission and quarantine

- **Status:** Proposed for M1 review
- **Date:** 2026-11-09

## Context
`InformationAvailability` requires aware timestamps but cannot represent an
adapter's missing, approximate, or unverified release claim. Constructing it
directly from an estimate erases uncertainty before historical version selection.
Raw claims need an explicit boundary that retains the rejected input and explains
why it cannot enter the validated time contract.

## Decision
`data.admission` adds frozen `RawTimestampClaim` records with a parsed datetime,
date, or missing value; original source text; `TimestampStatus` (`exact`,
`unknown`, `approximate`, `unverified`); evidence reference; and uncertainty
reason. It performs no parsing. Adapters must preserve a date as a date and must
never upgrade it to a fabricated aware midnight. Missing/unparsed values remain
`None`; original text can retain an unparseable source value. `source_text` is
optional and retains the original text when supplied. An exact claim may omit it
if the required timestamp and evidence reference satisfy admission.

`RawAvailability` binds a stable `ObservationKey` and version ID to separate
publication/provider claims, event time (possibly unknown), and local ingestion
time. `admit_availability` returns `AcceptedAvailability` or
`QuarantinedAvailability`. Each retains the unchanged raw envelope. Accepted
results contain a UTC-normalized `InformationAvailability`; quarantined results
contain an immutable tuple of field-specific reasons and no validated envelope.
Direct result construction rechecks its admission state.

Both publication and provider claims must have exact status, an aware datetime,
a nonblank evidence reference, and no nonblank uncertainty reason. A declared
uncertainty cannot be overridden by an exact label. Missing values, dates, naive
datetimes, uncertain statuses, missing evidence, and declared uncertainty produce
quarantine. Uncertain claims without a nonblank uncertainty reason also report
that omission. Reasons accumulate for both fields in publication/provider order.
Unknown event time is permitted; a known future event does not delay an earlier
announcement. Naive event/ingestion timestamps also quarantine. All supplied
datetimes must roundtrip through UTC to the same civil time and UTC offset.
Nonexistent local times, such as 02:30 in New York's spring DST gap, quarantine
rather than normalizing to an invented instant. Both valid fall folds remain
admissible and normalize to their distinct UTC instants. Wrong API types,
including strings in parsed timestamp fields or claims in place of datetime
envelope fields, raise `ValueError`.

Evidence references are assertions by the adapter. A nonblank string does not
authenticate a release instant, prove that the reference belongs to this version,
or establish that the referenced evidence exists. Each amendment must carry its
own availability evidence; the boundary never inherits evidence from an earlier
version. It cannot detect an adapter copying or mislabeling a reference. Adapters
remain responsible for inspecting source evidence and preserving its relationship
to the version, parsed precision, and original text.

## Scope and consequences
This is an in-memory syntactic admission policy. Quarantine is a returned value,
not durable storage, a queue, or a record of completed processing. No provider,
dependency, persistence system, accounting convention, or trading path is added.
Source URI, license ID, checksum, revision rank, and retraction fields remain
validated separately by `ObservationVersion`; adapters must verify their meaning
and the digest against actual content. The raw envelope contains no payload.

Existing `core.time` and `data.versions` contracts remain unchanged. Accepted
timestamps do not by themselves satisfy version provenance, data quality, or
operational eligibility. Historical replay still ignores backfill ingestion;
operational consumers still require explicit completed processing through
`is_available_to_platform_at`. Raw envelopes and admission results cannot enter
`VersionCatalog` directly: a validated `ObservationVersion` is still required.

Deterministic reference cases cover both missing and uncertain release fields,
date-only/naive claims, contradictory uncertainty, absent evidence, unknown/future
events, historical backfills, optional source text, UTC offsets, nonexistent
spring DST times and valid fall folds, operational processing,
catalog revision boundaries, and an amendment lacking evidence while the prior
version stays selectable. Source-specific evidence authentication, durable raw
storage/quarantine, provider ingestion, effective-dated joins, and snapshots
remain future work. No M1 checkbox is closed by this slice or by local checks.
