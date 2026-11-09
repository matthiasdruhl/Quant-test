# ADR 0011: Explicit raw receipt sets and assertion-quality reports

- **Status:** Proposed for M1 review
- **Date:** 2026-11-09

## Context

Persisted admission receipts retain raw assertions but cannot describe an explicit
collection or summarize its admission/null characteristics. Counting payload files
would merge distinct receipts with identical bytes and could include unrequested
objects. A reproducible inventory must pin receipt identities and verify each
receipt and its referenced payload before reporting a result.

## Decision

`data.receipt_sets` adds frozen `ReceiptSetManifest`, `RawReceiptSet` and nested
`ReceiptSetQualityReport`, `ReleaseFieldQuality` and `QuarantineReasonCount`
contracts. `build_receipt_set(archive, receipt_sha256s)` requires a
`LocalRawArchive` and an explicit built-in tuple/list of exact lowercase SHA-256
receipt digests. Invalid containers/entries and duplicate digests reject before
reading. Membership is copied into a sorted immutable tuple. An explicit empty
collection is valid and yields zero counts, including both release-field records.
There is no discovery, directory scan, implicit inclusion, or revision selection.

Every requested digest is loaded through `LocalRawArchive.get_receipt`, verifying
receipt bytes, raw policy, recomputed admission and exact referenced payload.
Distinct receipt digests remain distinct even when payload, observation key or
version ID is the same. No payload deduplication changes the report denominator.
Accepted and quarantined receipts both remain inventory members.

The deterministic `raw-receipt-quality-v1` report contains counts only:

- `receipt_count` is the number of distinct explicitly selected receipt digests.
  `accepted_count` and `quarantined_count` partition this denominator under
  `raw-availability-v1`; they do not mean validated or evaluable observations.
- `unknown_event_time_count` counts `raw.event_at is None` among all receipts.
  Unknown event time is permitted by admission; this is descriptive information.
- Each release field (`published_at`, then `source_available_at`) uses all
  receipts as its denominator. Null counts separately cover `parsed_value`,
  `source_text`, `evidence_reference` and `uncertainty_reason`; null means `None`,
  not blank/empty text. Date-only counts include `date`, excluding `datetime`.
  Exact/unknown/approximate/unverified status counts partition all receipts.
  These dimensions overlap: an unknown claim may also have a null parsed value.
  Optional source text may be absent on accepted receipts; absent uncertainty
  reason is normal on exact claims. Null counts are not automatic defect counts.
  Blank evidence can cause quarantine while its null count stays zero.
- Quarantine groups use exact `(field, reason)` strings, sorted lexicographically.
  Each group counts quarantined receipts containing that pair, once per receipt.
  Event and ingestion issues are included as well as release issues. A receipt
  can have multiple reasons, so group totals may exceed quarantined count.
  Zero-occurrence groups are omitted; an empty inventory has no groups.

No percentages, missing denominators, source coverage, completeness inference,
quality score, or repaired/fabricated values are provided. Policy changes to these
meanings require a new explicit policy version.

`encode_receipt_set` produces schema-version-1 canonical ASCII JSON using sorted
object keys, compact separators, escaped non-ASCII and no trailing newline. One
content-addressed object contains the manifest and report together, plus explicit
admission and quality policy IDs. This avoids a separate report object that could
be orphaned or paired with the wrong manifest. The independent literal fixture
`tests/fixtures/raw-receipt-set-v1.json` pins the complete shape and exact bytes.
The encoder alone serializes an assertion and does not verify an archive.

`LocalRawArchive.put_receipt_set(receipt_sha256s) -> str` rebuilds/validates the
collection before publishing that canonical manifest/report object last through
existing `put`; it returns its separate SHA-256. It writes no new receipt/payload.
The caller retains the digest externally; there is no index or discovery API.
`get_receipt_set(digest) -> RawReceiptSet` verifies the object checksum and calls
`decode_receipt_set(payload, archive)` to reopen every member through
`get_receipt`, recompute the report, and require exact canonical byte equality.
Duplicate JSON keys at any depth, missing/unknown fields, unsupported schema or
policy, floats/nonfinite numbers, booleans substituted for integers, noncanonical
bytes, unsorted/duplicate membership and any changed summary reject. Rehashing a
false report does not make it valid. This checks assertions, not source evidence.

## Failures and scope

Invalid API arguments raise `ValueError`; standalone decoding raises
`ReceiptSetFormatError`, a `ValueError` subtype. `ReceiptSetMissingError` and
`ReceiptSetCorruptError` inherit `RawArchiveError` and distinguish missing object
from invalid checksum, format, policies or report. Member receipt failures retain
`ReceiptMissingError`/`ReceiptCorruptError`; referenced payload failures retain
`PayloadMissingError`/`PayloadCorruptError`; filesystem failures retain
`ArchiveIOError`. Any missing/corrupt member fails the operation; no fallback,
partial report, or silent member removal is returned.

No new manifest is published if dependency verification or pre-link publication
fails. Existing complete objects are never repaired/replaced. ADR 0009's trusted
local POSIX filesystem, no-replace protocol and failure semantics apply unchanged:
cleanup or directory-close failure can raise after a complete object is linked;
retry verifies that object, without removing abandoned staging files. There is
no fsync, crash durability, multi-object crash transaction, recovery or garbage
collection. Caller-controlled root permissions/capacity and exclusion of hostile
mutation remain required. Reopen checks current dependencies, not durable proof
that those objects can never disappear.

This inventory is not a reproducible dataset snapshot. It carries no decision
cutoff, revision choice, validated observation promotion, code/environment pin,
transform lineage, provider coverage or completeness guarantee. It authenticates
neither source/evidence/license assertions nor actual completed processing. Raw
receipt membership grants no historical/operational catalog eligibility. Provider
ingestion, financial/trading behavior, quarantine workflows, services and new
dependencies remain outside this slice. All M1 boxes remain open.

## Evidence

Deterministic tests use a literal independent canonical fixture and independently
specified mixed-receipt counts. They exercise empty collections, order invariance,
input snapshots, same-payload/same-key/version distinct receipts, optional null
text without quarantine, all status/null/date dimensions, multiple exact reason
groups, nonrelease issues, immutable results, strict rehashed tampering, missing/
corrupt selected objects, dependency-first failure and pre/post-publication fault
semantics. Existing archive and receipt tests retain lower-level byte/temporal
checks. Local checks establish neither remote CI nor independent owner approval,
real provider behavior or crash durability.
