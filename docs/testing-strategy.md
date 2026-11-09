# Testing and verification plan

## Fast checks
CI is configured to run `ruff check .`, `ruff format --check .`, `mypy src`, and `pytest` on the exact Python baseline in `.python-version`, on Ubuntu and macOS. It additionally builds/installs a wheel and checks that the data/time modules import; pytest then exercises the installed distribution. Local checks use the same hash-locked installation described in [environment setup](environment.md). A workflow file is not evidence of a successful remote run.

## Test layers
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

Adapters must still authenticate provenance, prove identity and complete source
history scope, and persist raw metadata/quarantine records. The local archive
persists only payload bytes. Provider coverage/completeness,
derived lineage, target processing, holdout access control, backtest correctness,
and financial invariants remain **unimplemented** and must not be marked complete.

Before M1 acceptance, independent cases must exercise unknown availability quarantine, revisions, effective-dated mappings, and universe joins. Before M3 acceptance, exercise [target reference cases](decisions/0004-target-exposures.md), future-trained artifacts and preprocessors, and [holdout lifecycle failures](research-protocol.md). Before M7 acceptance, prove operational consumers cannot fall back to historical-only availability or bypass the independent risk gate. Documented scenarios must become executable tests in the owning milestone; prose alone does not satisfy these gates.

## Pull request acceptance
- Small, coherent task and explicit non-goals.
- Tests covering normal and failure modes.
- Logs of checks actually run.
- Migration/ADR for public contract changes.
- Benchmark or profiling evidence before performance abstractions.
- Human approval for financial conventions, dependencies, and any eventual brokerage access.
