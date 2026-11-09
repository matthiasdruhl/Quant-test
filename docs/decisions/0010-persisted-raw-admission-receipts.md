# ADR 0010: Persisted raw admission and quarantine receipts

- **Status:** Proposed for M1 review
- **Date:** 2026-11-09

## Context

ADR 0006 retains raw claims and admission results only in memory. ADR 0009 stores
exact payload bytes but does not associate them with a source claim, license
identifier, or quarantine decision. Retaining a rejected raw input for inspection
requires both its exact bytes and the claims that caused rejection. A payload
checksum alone cannot distinguish identical bytes asserted by different sources
or versions. Promoting a syntactic acceptance into a validated observation would
also hide the remaining source and revision validation work.

## Decision

`data.receipts.AdmissionReceipt` is frozen and binds `RawAvailability`, exact
nonblank `source_uri` and `license_id` strings, and a lowercase payload SHA-256.
Construction recomputes `admit_availability` into its derived `result`; callers
cannot supply an outcome. The policy identifier is `raw-availability-v1`. This
names the current ADR 0006 syntactic policy, including exact required claims,
nonblank evidence references, UTC roundtrip checks and ordered field-specific
quarantine reasons. Changes to its behavior or reason strings require an explicit
policy version decision; old receipts are not silently upgraded.

The standard-library codec `encode_receipt`/`decode_receipt` uses schema version
1 and deterministic ASCII JSON: sorted object keys, compact separators, escaped
non-ASCII text, no trailing newline. Every documented field is required; no
unknown fields, duplicate object keys, unsupported numbers, unknown schema/policy,
or alternative noncanonical representation is accepted. The independent fixture
`tests/fixtures/admission-receipt-v1.json` pins the complete schema and byte format.
The schema includes the full raw envelope/provenance, payload digest, policy,
and either accepted UTC availability fields or ordered quarantine reasons.
Loading recomputes admission and byte-compares the encoded result before requiring
the entire decoded receipt to reproduce the original canonical bytes. A stored
result or unknown field cannot be accepted just because the receipt digest was
recomputed after editing it.

Raw timestamps encode `None`, date-only values, and datetimes distinctly. Dates
use canonical ISO dates. Datetimes store a canonical naive civil timestamp with
six fractional digits, fold 0/1, and an explicit timezone representation. A civil
field containing an ISO offset rejects; it is never reinterpreted as a different
zone. Naive times remain naive and quarantined where required. UTC has its own
tag. Standard fixed offsets retain their exact integer microseconds and name.
Keyed `ZoneInfo` values retain their key, fold, observed UTC offset and zone name.
Loading reconstructs that key and requires the current rules to reproduce the
recorded civil offset/name, failing explicitly if the key is unavailable or rules
differ. Encoding likewise requires the key to be resolvable with matching rules.
Both folds in a spring gap remain that same nonexistent civil time and quarantine;
valid fall folds remain distinct UTC instants. Datetime/date subclasses and other
`tzinfo` implementations reject only at the codec boundary. Existing in-memory
constructors are unchanged. This does not bundle or pin a timezone database;
a matching rule check establishes only the represented timestamps, not complete
tzdb equivalence.

`LocalRawArchive.put_receipt(receipt, payload) -> str` encodes/validates the receipt,
verifies and stores the exact payload first, and publishes the encoded receipt
last, returning its separate SHA-256. Both are ordinary immutable content-addressed
objects under the same trusted flat root and ADR 0009 no-replace protocol. Repeated
puts verify both existing objects. Equal payload bytes may share an object while
distinct raw identity, versions, source/license/evidence claims or outcomes produce
distinct receipt digests. The archive adds no mutable index or discovery API;
callers must retain the receipt digest externally.

`LocalRawArchive.get_receipt(receipt_sha256) -> AdmissionReceipt` verifies receipt
bytes, strictly decodes/recomputes admission, then verifies the exact referenced
payload before returning. It never searches for or substitutes another receipt,
observation version, or readable earlier payload. `ReceiptMissingError` and
`ReceiptCorruptError` inherit `RawArchiveError`. Corruption includes nonregular
receipt objects, digest mismatch, malformed schema/policy, or inconsistent result.
`ReceiptFormatError` is a `ValueError` from the standalone codec. Referenced payload
failures retain `PayloadMissingError`/`PayloadCorruptError`; filesystem failures
retain `ArchiveIOError`. Invalid API arguments raise `ValueError`.

## Publication and failure limits

Before receipt publication, failure cannot expose a new complete receipt. Payload
mismatch and unsupported codec values fail before writing; failure while storing
the payload prevents receipt publication. Failure during receipt staging,
verification or linking may leave the already verified payload unreferenced.
Existing complete receipts are never replaced or repaired.

ADR 0009's post-publication distinction remains: failed staging cleanup or directory
close can raise after the verified receipt has been atomically linked. Such an
exception does not prove absence of a complete receipt. Retrying verifies existing
content; it does not remove abandoned staging files. Tests explicitly distinguish
pre-publication failure from cleanup failure after linking. No fsync, crash
atomicity across objects, crash durability, recovery, automatic garbage collection,
or hostile mutation protection is added. The caller must control the trusted
local POSIX root and retain the existing capacity, permissions and concurrency
assumptions. Read-only modes remain accidental-write safeguards.

## Non-goals and evidence

A receipt records adapter assertions and a syntactic policy result. It does not
authenticate evidence, prove source identity or license rights, establish provider
coverage or source revision order, create `ObservationVersion`, or establish
completed ingestion/processing. Receipt publication and loading do not alter
historical or operational eligibility contracts. Catalogs still require separately
validated observation versions. This is raw receipt retention, not a provider
adapter, quarantine queue/reprocessing workflow, normalized metadata store,
dataset manifest, OHLCV/corporate-action feed, or evaluable dataset.

No dependency, database, service, provider, deployment, account creation, financial
convention or trading path is introduced. This is a narrow extension of ADRs 0006
and 0009; all M1 gates remain open for complete evidence, CI and independent review.
Deterministic tests pin independent canonical bytes/digests and release cutoffs,
accepted/quarantined reopen, raw precision/text/uncertainty, gap/fold and fixed
zone representation, amendment quarantine, identical-payload provenance,
strict rehashed tampering, missing/corrupt objects, publication ordering/failures
and retry after post-publication cleanup failure. Local tests do not establish
remote CI, independent approval, real provider behavior or crash durability.
