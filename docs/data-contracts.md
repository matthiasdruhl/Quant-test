# Data contracts (design draft)

## Core identifiers
Use stable security IDs with issuer/security mappings and effective dates. Tickers are display symbols, not permanent identities. Exchanges, currencies, delistings, and corporate actions need explicit definitions.

## Time and provenance
For every external observation store:
- `event_at`: when the economic activity or underlying event occurred (if known).
- `published_at`: when this version of the content was first publicly released.
- `source_available_at`: when the selected provider actually made this version available.
- `ingested_at`: when our infrastructure fetched/recorded it.
- `source_id`, `source_uri`, `license_id`, `version_id`, and content checksum.
- An uncertainty/missing marker for timestamps that cannot be proven.

Raw ingestion records may retain null timestamps with a reason and source evidence; ingestion must not invent timestamps, substitute event time for release time, or silently parse a date into a midnight release. Unknown `event_at` is permitted because an event may be undated or announced in advance. Unknown or uncertain publication/provider availability makes a raw observation **ineligible**: quarantine it until evidence establishes exact availability. Approximate dates, estimated lags, and unproven vendor claims must not enter the validated contract. A future policy for proven conservative bounds requires an ADR and reference cases.

`core.time.InformationAvailability` is the validated timestamp envelope, not the raw ingestion record. `event_at` accepts `None`; publication, provider availability, and ingestion must be timezone-aware datetimes. Missing, unparsed, and naive required timestamps raise `ValueError`. Provenance evidence remains the adapter's responsibility: the type cannot authenticate timestamps or make an uncertain estimate proven.

### Eligibility by mode
- **Historical source replay:** `first_usable_at = max(published_at, source_available_at)` by UTC instant; the property returns UTC. `is_usable_at(T)` accepts equality and ignores backfill ingestion time. This reconstructs information accessible through the selected historical source, not information our platform actually observed. All comparisons normalize to UTC, including DST folds.
- **Operational observation:** `is_available_to_platform_at(T, processed_at=...)` additionally requires ingestion and completed local validation/processing no later than T. `processed_at` must be proven for this version and cannot precede ingestion. Missing processing evidence denies eligibility. Paper consumers must use this gate upstream of the shared strategy logic. No paper/live adapter exists yet.
- Both gates are necessary timestamp checks only. Data quality, as-of version selection, derived lineage, stale-input policy, and execution authorization are separate requirements. Timestamp equality does not authorize filling at the same bar's close: the scheduler must establish decision and fill ordering before M2 research use.

For each security/source/observation key, select the latest version eligible at the decision cutoff, never the latest version in today's database. Keep revisions immutable. Define a source-specific revision order and explicit tie-breaker; ambiguous duplicates, contradictory ordering, and unsupported retractions fail validation rather than selecting arbitrarily. Identifier mappings and universe membership must use their own effective dates and historically eligible versions. M1 must exercise revisions and temporal joins with independent fixtures.

`data.versions` implements only the in-memory historical selection rule for validated metadata. Its source-assigned integer revision ranks, uniqueness checks, and tie-break rule are specified in [ADR 0005](decisions/0005-observation-revision-selection.md). Raw quarantine, source-order proof, provider ingestion, effective-dated joins, and persistence remain M1 work; a selected metadata version alone is not an evaluable dataset.

### Derived features and model artifacts
Every derived output must pin input snapshot/version IDs, transform code and parameters, artifact ID/checksum (if any), and its actual computation/completion timestamp. Artifacts must record their release/first-usable time, training-data cutoff and snapshot IDs, fitted preprocessing/calibration, and tuning/selection lineage. Preprocessing and model fitting must use only the permitted training partition. Unknown training provenance makes an artifact ineligible for historical predictive evaluation; it may still produce explicitly labeled exploratory proposals.

In historical replay, a deterministic recomputation may occur today, but all its input versions and any fitted artifact must have been usable by the simulated decision. Derived historical availability is no earlier than the maximum of those dependencies' eligible availability times. A model trained or released after T cannot generate a supposedly available forecast at T. Choosing a transform using later outcomes is strategy selection and is subject to the research protocol, even if the underlying inputs are old.

For operational use, the derived output must also have actually completed validation/processing and reached its consumer by T; source timestamps cannot stand in for that completion. Source and artifact lineage is recursive, so an eligible final timestamp cannot conceal an ineligible dependency. The current timestamp primitive does not implement a feature/artifact lineage validator. M3/M4/M5 cannot claim these gates complete until their respective consumers enforce them and adversarial future-artifact cases pass.

## Market bars
A bar needs a stable security ID, trading venue, interval start/end, currency, raw OHLCV, vendor, adjusted/raw convention, source revision, and availability metadata. Define exact bar-completion and next-execution rules before research use.

## Corporate actions
Preserve split ratios, cash/stock distributions, effective/ex dates, announcements, and observation versions. Never double-count adjustments in both bar data and position accounting.

## Filings and disclosures
Preserve filing identity, amendment chain, submitted/public timestamp, covered reporting period, beneficial-owner/manager ID, security mapping, and reported value-range/precision. A 13F quarter-end holding is not a contemporaneous trade. Politician filings often disclose ranges, not exact amounts; do not fabricate sizes.

## Alternative data
Enforce license rights, geographic/store mapping, observation quality, coverage gaps, time-of-day/seasonality metadata, and estimated cost. Satellite data must record acquisition and delivery timestamps separately.

## Dataset snapshots
Immutable manifest: source versions, transforms and checksums, code revision, as-of cutoff, coverage report, and anomaly counts. Pin the environment manifest/hash and applicable transform/artifact lineage. Store repository-local raw datasets in `/data/`, generated artifacts in `/artifacts/`, and exported results in `/outputs/`; these root directories are ignored, while `src/quant_test/data/` is source code. Invalid/unknown values should produce explicit flags, not automatically filled zeroes.

See [environment requirements](environment.md), [research protocol](research-protocol.md), and [ADR 0002](decisions/0002-information-eligibility.md).
