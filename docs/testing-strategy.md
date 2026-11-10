# Testing and verification plan

## Fast checks
CI is configured to run `ruff check .`, `ruff format --check .`, `mypy src`, and `pytest` on the exact Python baseline in `.python-version`, on Ubuntu and macOS. It additionally builds/installs a wheel and checks that the data/time modules import; pytest then exercises the installed distribution. Local checks use the same hash-locked installation described in [environment setup](environment.md). A workflow file is not evidence of a successful remote run.

The same workflow runs on pushes to `main` and `codex/**` branches and on pull
requests, so a pushed implementation branch can receive CI without opening a PR.
Push runs check out the pushed revision; PR runs use GitHub's synthetic merge
revision under the current checkout configuration. Record the actual checked-out
SHA from job logs when reporting evidence; a run associated with a PR head does
not prove that the literal head was tested. Trigger coverage does not authorize
merging, deployment or milestone completion.

## Test layers
The layers below are the verification plan. Currently, `tests/unit/` contains the
timestamp suite and `tests/contract/` contains the data reference, cross-module,
and adversarial cases described below. `tests/integration/` contains only a
`.gitkeep`. Hypothesis is a locked development dependency, but no property-based
suite is implemented. End-to-end ingestion, strategy, ledger, and research layers
await their owning milestones.

1. **Unit:** deterministic parsers, timestamps, calculations, validation, negative paths.
2. **Contract:** provider/strategy/portfolio interfaces and hand-calculated accounting fixtures.
3. **Property:** monotonicity/invariants using Hypothesis; random valid and invalid sequences.
4. **Integration:** data ingestion → as-of features → strategy → simulated order → ledger.
5. **Adversarial:** look-ahead traps, delayed releases, delistings, zero volume, holidays, splits, duplicated fills, reconnects, partial fills.
6. **Research:** out-of-sample stability, baselines, fees, market-regime comparisons, multiple-hypothesis selection controls.

## Independent evidence
Reference fixtures must be constructed from an external calculation or human-readable specification, not copied from implementation results. A separate reviewer checks the acceptance contract and can add failing cases. Do not weaken a test merely to make a PR pass.

## Scope of current scaffold
Timestamp availability, in-memory historical observation-version selection, raw
admission/quarantine results, historical listing lookup, and universe membership/
listing joins have implemented test
suites. Timestamp/revision cases cover release boundaries, missing/naive values,
ambiguous ordering, offsets, future announcements, and actual platform
ingestion/processing boundaries for the timestamp primitive. Raw admission tests
exercise uncertain claims, evidence assertions, and DST gaps/folds. Listing
reference cases independently specify initial/rename/delist boundaries, ticker
reuse, late corrections, removed intervals without fallback, eligible symbol
ambiguity, exact source/venue partitions, immutable histories, provenance on
absent matches, and real DST instants. These use hand-specified fixtures, not
provider records or implementation-generated expected values.

Membership references specify inclusive entry/exclusive exit, delayed removals,
late corrections, complete replacements without fallback, negative provenance,
source/universe isolation, immutable input snapshots, deterministic ordering and
DST folds/gaps. Join references require the same E/D while selecting each source's
own eligible revisions, retain delisted members as explicit unresolved IDs, prove
ticker reuse preserves stable IDs, and preserve distinct same-symbol member IDs
while explicit symbol resolution rejects ambiguity.
Unknown raw availability remains quarantined and cannot enter these catalogs.
See [ADR 0008](decisions/0008-point-in-time-universe-membership.md).

Local raw archive references use independently specified SHA-256 `abc`/empty
vectors and exact binary payloads. They verify reopen/idempotency, mismatch before
write, missing/corrupt content, invalid arguments and roots, symlink/directory/FIFO
rejection, short and zero-progress writes, staged-byte verification, injected
filesystem failures, no-replace competing publication, and cleanup failure after
successful publication. A hand-specified late correction selects eligible
metadata first, then proves that missing/corrupt selected content raises despite
an older readable payload. These deterministic injected faults do not establish
crash durability or real concurrent stress; see
[ADR 0009](decisions/0009-local-raw-payload-archive.md).

Raw admission receipt references independently specify canonical schema-1 JSON
bytes/digest and release cutoffs. They verify accepted/quarantined reopen and
idempotency, exact raw/source/license/evidence/uncertainty text, distinct date/
datetime/unknown values, UTC and named fixed offsets, keyed ZoneInfo civil times
and both folds. Nonexistent gap times remain quarantined; valid folds retain
independently specified UTC instants. Unsupported timezone/subclass values reject
at the codec boundary. Rehashed schema/policy/result tampering, duplicate/unknown/
missing fields, invalid types and noncanonical JSON fail explicitly. Identical
payload bytes with distinct provenance yield distinct receipts; a quarantined
amendment cannot enter the catalog while the separately validated prior version
remains selectable. Missing/corrupt receipts and referenced payloads fail without
fallback. Injected pre-publication failures prevent a new receipt, allowing an
unreferenced verified payload; post-link cleanup failure can leave a complete
receipt and retry verifies it. See
[ADR 0010](decisions/0010-persisted-raw-admission-receipts.md).

Raw receipt-set references pin independent literal schema-1 canonical bytes and
hand-specified receipt denominators and counts. They exercise order/input snapshots,
explicit empty sets, identical payload/key/version with distinct receipts, optional
null text without quarantine, all claim statuses, date-only/null counts, multiple
field/reason groups and event/ingestion issues. Strict rehashed report/schema/policy
tampering, nested duplicate keys and noncanonical JSON reject. Missing/corrupt
manifest/member/payload fails without fallback or repair. Dependency verification
precedes publication; injected link failure leaves no manifest, while cleanup
failure after linking leaves a verified complete object that retry checks. These
local tests imply no provider coverage, completeness, dataset snapshot, CI result
or crash durability; see
[ADR 0011](decisions/0011-raw-receipt-set-quality-report.md).

Receipt-linked observation references pin independent literal canonical bytes/hash
and every shared-field mismatch. They exercise exact text, accepted/quarantined
receipts, unknown events, equivalent offsets, both DST folds, gaps before UTC
normalization, unsupported datetime/integer/timezone boundaries, UTC overflow and
keyed-zone offset/name mismatch. Rehashed nested schema/policy/type/timestamp
tampering and duplicate/noncanonical JSON reject. Missing/corrupt/nonregular
metadata and dependencies fail without fallback or repair. Injected creation,
write, file-close, stage verification and link failures expose no new metadata;
post-link cleanup/directory-close failure can leave a complete object that retry
verifies. Reopened versions compose with existing revision cutoffs and operational
processing gates. Explicit rank assertions remain unauthenticated; these cases
prove linkage mechanics, not provider truth, source coverage or milestone
acceptance. See [ADR 0012](decisions/0012-receipt-linked-observation-records.md).

Version-catalog inventory references pin literal canonical manifest bytes/hash,
explicit empty membership and invalid-archive/collection rejection before reads.
They exercise input snapshots, digest order/provenance, manifest correspondence,
duplicate version IDs/ranks across distinct records/receipts, contradictory
availability, independent key partitions, equal-time rank ties and historical
backfill boundaries after reopen. Rehashed schema/policy/type/membership tampering,
unknown/duplicate fields, unsorted arrays and noncanonical bytes reject. Missing/
corrupt/nonregular manifests and any record/receipt/payload failure prevent a
complete result; raw receipts/payloads cannot enter as observation records.
Publication fault cases preserve dependency-first ordering, pre-link failure and
post-link cleanup/directory-close retry semantics. These inventories make no
provider coverage, source authentication or evaluable dataset claim. See
[ADR 0013](decisions/0013-version-catalog-inventories.md).

Listing-history record references independently pin a fresh literal listing-key
receipt/observation/listing byte-and-hash chain. Reopened histories exercise rename,
delist, late correction, empty replacement, negative provenance, ticker reuse and
multiple venues under existing effective/decision cutoffs. Tests cover all supplied
version mismatches, exact interval text/order, offset and DST semantics, standard
endpoint type/fold normalization, strict nested field/type/schema/policy/canonical
tampering and every selected dependency failure. Valid changed interval/reference
assertions remain distinct and do not claim source parsing authentication.
Injected creation/write/close/verify/link and post-link cleanup/directory-close
failures retain archive publication/retry semantics. See
[ADR 0014](decisions/0014-persisted-listing-history-records.md).

Membership-history record references pin fresh literal receipt/metadata/membership
bytes and hashes with an exact whitespace/colon universe suffix. Reopened temporal
cases cover entry/exit, late corrections, empty replacements with negative
provenance and security/source/universe isolation. Cross-module references reopen
listing records and apply independent release cutoffs, preserving unresolved
delisted members despite ticker reuse and later mapping corrections. Tests cover
every supplied-version/universe mismatch, valid new assertions, ordered intervals,
offset/fold/gap/subclass boundaries, forbidden listing fields, strict schema/types/
canonical bytes, dependency corruption and pre/post-publication faults. These
mechanical references prove neither source parsing nor real-world universe
completeness. See
[ADR 0015](decisions/0015-persisted-membership-history-records.md).

Universe-listing replay references pin independent literal artifact bytes/hash,
dependency IDs and selected interval indices, then reopen a fresh archive. Cases
cover independent release/correction cutoffs, selected negatives/empty per-key
replacements, missing versus selected-negative mappings, unresolved delistings,
ticker reuse and equal symbols on distinct stable IDs. Original unsorted tuple
indices, full key/version association, exact filters, immutable sorted membership,
empty collections and scalar UTC/timezone/fold/gap/overflow boundaries are tested.
Both whole catalogs reject future/irrelevant contradictions before filtering.
Strict schema/report/type/order/canonical tampering and statically impossible
reports reject before dependency reads where possible; recomputed equality catches
semantic report drift. Every missing/corrupt graph node and wrong-typed reference
fails without partial joins, fallback or repair. Dependency-first and injected
pre/post-publication faults preserve archive retry semantics. Valid changed
queries/dependencies with correct reports remain new assertions, not proof of
source truth or complete research reproducibility. See
[ADR 0016](decisions/0016-historical-universe-listing-replay.md).

Adapters must still authenticate provenance and prove identity and complete source
history scope. The local archive persists exact payloads, raw receipt assertions/
outcomes, individually linked version assertions and explicit metadata inventories;
it does not implement a quarantine queue/reprocessing workflow. Provider
coverage/completeness, derived lineage, target processing,
holdout access control, backtest correctness, and financial invariants remain
**unimplemented** and must not be marked complete.

Before M1 acceptance, independent cases must exercise unknown availability quarantine, revisions, effective-dated mappings, and universe joins. Before M3 acceptance, exercise [target reference cases](decisions/0004-target-exposures.md), future-trained artifacts and preprocessors, and [holdout lifecycle failures](research-protocol.md). Before M7 acceptance, prove operational consumers cannot fall back to historical-only availability or bypass the independent risk gate. Documented scenarios must become executable tests in the owning milestone; prose alone does not satisfy these gates.

## Locked-toolchain replay references

Development-verifier tests pin independent literal canonical input bytes/hash
and strict marker/lock/wheel identity cases. Minimal ZIP fixtures exercise parsing
only and are never installed or evidence of real lock completeness. Missing,
extra, duplicate, unsafe or incompatible wheels, contradictory filename/metadata/
WHEEL tags, changed lock/local hashes and source-lock disagreement fail preflight.
Manifest tampering, seeded/editable/duplicate inventories, process failures,
incorrect import/platform provenance, zero tests, staged/input mutation and
publication failures prevent success. Process doubles test sequencing only;
executable isolated probes exercise the observation code and explicit development
script imports from outside the checkout without adding source paths.

The complete positive case is the separate CI verifier invocation after real
hash-verified wheel materialization and package build: capture/read back, fresh
unseeded offline install, exact inventory/`pip check`, installed imports and the
actual test suite, then postchecks/report publication. It is never recursively
invoked from that suite. Existing `verify_hash_install.py` CLI/negative checks
remain unchanged. Run `mypy scripts/verify_toolchain_replay.py` in addition to the
mandatory source check. No complete experiment reproducibility, bootstrap
security, durable retention or CI success is inferred from unit doubles or this
configured workflow; see [ADR 0019](decisions/0019-offline-toolchain-replay.md).

## Target quantity and lifecycle references

`strategies.targets` cases independently specify A .10/B .20 replaced by A .05,
stream isolation, explicit zero/active empty distinctions, future decisions,
half-open expiry and latest-expired selection without fallback. Tests cover every
expected context field, per-role snapshot identity, global future batch conflicts/
decision ties, normalized retries retaining first assertions and immutable input
snapshots. Decimal validation exercises explicit units/types, sNaN/NaN/infinity,
huge exponents and ambient precision/traps without arithmetic or rescaling.
Real-time cases cover equivalent offsets, keyed-zone reproduction, folds, gaps,
unsupported scalar/container values and UTC overflow. Direct selections validate
correspondence and derive status/targets but do not prove latest history selection.
Cross-module references keep source/operational availability distinct and show
that a retained replay digest is only a caller snapshot assertion here. These
cases do not verify source truth, actual target arrival/current portfolio, sizing,
allocation, accounting or strategy performance. See
[ADR 0018](decisions/0018-immutable-target-batch-lifecycle.md).

## Proposed M2 ledger references

[ADR 0017](decisions/0017-explicit-reference-ledger.md) and the
[five reference scenarios](m2-reference-ledger-v1.md) provide reviewable proposed
units, fill/settlement arithmetic, reservations, identity/retry behavior and
explicit valuation inputs. They are hand-calculated specifications, not executed
ledger tests or accepted financial defaults. The human-approval requirement below
applies before runtime implementation: record owner approval of the exact
revision's five decisions, scope and references. After approval, a separate
implementation must add independent executable scenarios and negative invariants,
then receive independent review and exact-revision CI. Existing checks on this
docs-only proposal verify the repository, not accounting runtime or milestone
acceptance.

## Pull request acceptance
- Small, coherent task and explicit non-goals.
- Tests covering normal and failure modes.
- Logs of checks actually run.
- Migration/ADR for public contract changes.
- Benchmark or profiling evidence before performance abstractions.
- Human approval for financial conventions, dependencies, and any eventual brokerage access.
