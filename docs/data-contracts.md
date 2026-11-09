# Data contracts (design draft)

## Core identifiers
Use stable security IDs with issuer/security mappings and effective dates. Tickers are display symbols, not permanent identities. Exchanges, currencies, delistings, and corporate actions need explicit definitions.

## Time and provenance
For every external observation store:
- `event_at`: when the economic activity or underlying event occurred (if known).
- `published_at`: when the content was first publicly released.
- `source_available_at`: when the selected provider actually made this version available.
- `ingested_at`: when our infrastructure fetched/recorded it.
- `source_id`, `source_uri`, `license_id`, `version_id`, and content checksum.
- An uncertainty/missing marker for timestamps that cannot be proven.

An observation is eligible for a historical decision at T only when its recorded public/provider availability is not later than T. Do not substitute current ingestion time for historical availability. Missing availability evidence must be treated conservatively.

The initial `core.time.InformationAvailability` type captures these timestamps and checks temporal usability; it does not fetch external data or prove that vendors' claimed timestamps are correct.

## Market bars
A bar needs a stable security ID, trading venue, interval start/end, currency, raw OHLCV, vendor, adjusted/raw convention, source revision, and availability metadata. Define exact bar-completion and next-execution rules before research use.

## Corporate actions
Preserve split ratios, cash/stock distributions, effective/ex dates, announcements, and observation versions. Never double-count adjustments in both bar data and position accounting.

## Filings and disclosures
Preserve filing identity, amendment chain, submitted/public timestamp, covered reporting period, beneficial-owner/manager ID, security mapping, and reported value-range/precision. A 13F quarter-end holding is not a contemporaneous trade. Politician filings often disclose ranges, not exact amounts; do not fabricate sizes.

## Alternative data
Enforce license rights, geographic/store mapping, observation quality, coverage gaps, time-of-day/seasonality metadata, and estimated cost. Satellite data must record acquisition and delivery timestamps separately.

## Dataset snapshots
Immutable manifest: source versions, transforms and checksums, code revision, as-of cutoff, coverage report, and anomaly counts. Invalid/unknown values should produce explicit flags, not automatically filled zeroes.
