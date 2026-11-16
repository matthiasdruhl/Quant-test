# Proposed source contract: Databento Security Master

**Status:** qualification candidate; not selected. Account entitlement and usage
rights are unverified; ingestion is not approved.
**Reviewed:** 2026-11-10, against public documentation and repository revision `40ba0e0`.
**Outcome:** public evidence is insufficient for promotion into validated historical
catalogs. No provider data was fetched, account accessed, or adapter implemented.
All [M1 gates](../roadmap.md#m1--point-in-time-market-data) remain open.

**Owner context, 2026-11-10:** the owner reports no existing provider/dataset
entitlement for research and archival use. This records the owner's stated access
context, not a conclusion about a vendor's legal terms. Source selection and usage
rights remain open; no acquisition or integration is approved by this record.

## Scope and rationale

Proposed first slice: listing identities and listing/delisting changes for a small,
explicit set of securities with U.S. equity listings. This does not cover prices,
corporate-action accounting, index membership, or a complete U.S. security master.
Documenting a candidate creates no new service/dependency or procurement decision;
adoption and any resulting architectural changes still require repository review.

Three candidates were checked, without an exhaustive vendor evaluation:

| Candidate | Relevant official evidence | Qualification judgment |
| --- | --- | --- |
| Databento Security Master | Separate effective and record timestamps, listing/security/issuer identifiers, and retained delisting/relisting records. [Dataset guide](https://databento.com/docs/datasets/security-master), [schema](https://databento.com/docs/schemas/security-master). | Investigate first because its documented structure exposes the temporal/identity questions our catalogs need answered. This is not proof that those questions are resolved. |
| Massive ticker reference | Its FAQ says past-date lists are effective-dated records maintained today, without a parameter for earlier record versions. [Security-master FAQ](https://massive.com/knowledge-base/article/does-massive-have-a-downloadable-security-master). | The historical-date selector alone cannot establish what was known at an earlier decision. |
| Norgate U.S. stocks | Documents listed/delisted coverage and defines delisting relative to the country's trading environment. [Data FAQ](https://norgatedata.com/data-package-faq.php). | Coverage is relevant, but the reviewed FAQ does not establish exact per-version release evidence or an amendment replay contract. |

Databento's guide advertises global history from 2005-01-01, continued tracking
after delisting/relisting, and weekly updates. These are vendor statements, not
independently measured coverage. Exact coverage, gaps and entitlements for the
chosen pilot securities remain unverified. The guide also warns of ambiguous
NYSE suffix symbology; ticker matching must not supply identity proof.
[Dataset guide](https://databento.com/docs/datasets/security-master).

## Product, acquisition and usage rights

The product is Databento Security Master through the Reference API, specifically
`Reference.security_master.get_range`. No immutable dataset release or API/schema
version is pinned yet. A future acquisition must retain its request scope,
response/schema version when supplied, documentation revision evidence and exact
response bytes; this review date is not a dataset version.
[API contract](https://databento.com/docs/api-reference-data/security-master/security-master-get-range?lang=python).

The product page lists U.S. venues including Nasdaq, NYSE and NYSE American. Its
FAQ describes internal display/non-display use and prohibits external file/API
redistribution. This public summary does not establish the owner's entitlement,
historical replay rights, retention after termination, or permission to put real
fixtures in GitHub/CI. Confirm applicable agreement/order and identifier-specific
restrictions before acquisition. An open-source client license does not license
its data. No price, subscription or legal approval is asserted here.
[Product and usage FAQ](https://databento.com/security-master).

## Time and identity mapping

The schema defines `ts_effective` as effective time, `ts_record` as last change,
and `ts_created` as database addition. Listing/delisting dates have date precision.
It groups listings under `security_id` and securities under `issuer_id`, with
`listing_id` identifying a listing. Those scopes do not establish lifetime ID
stability through corporate events or equivalence to another provider's IDs.
[Field definitions](https://databento.com/docs/schemas/security-master).

The following are proposed adapter requirements under the existing
[data contracts](../data-contracts.md), not implemented conversions:

| Existing contract | Proposed treatment / blocking evidence |
| --- | --- |
| `ObservationKey.security_id` | Retain exact provider `security_id` in a documented provider namespace; require evidence for reuse, merges, splits and ID retirement before treating it as stable. Never derive an ID from ticker or substitute issuer ID. |
| `source_id`, `observation_id` | Register a source scope explicitly; listing histories retain the fixed `listing-history` observation ID. No namespace is registered by this document. |
| `ListingInterval.issuer_id`, `symbol`, `venue`, `currency` | Preserve issuer ID and native symbol (`local_code`) without ticker heuristics. Candidate venue fields are `exchange`, `operating_mic` and `segment_mic`; currency is `trading_currency`. The venue choice remains unresolved. Missing or ambiguous required values block an interval. A query's matched `symbol` is not sufficient identity evidence. |
| Effective interval endpoints / `event_at` | Establish the meaning of each effective timestamp before use. Preserve date-only facts outside instant fields; unknown event time remains `None`. Do not turn listing/delisting dates into midnight, session close, or an exclusive interval end. An instant convention needs an explicit reviewed decision and reference cases. |
| `published_at` | Require exact version-specific public-release evidence. None of the three timestamp names alone establishes this field. Missing evidence remains an unknown raw claim with a reason. |
| `source_available_at` | Require exact evidence of when this version became accessible through the selected provider product. Database modification/addition time is not automatically customer availability. |
| `ingested_at`, operational processing | Record actual local acquisition and completion independently. Neither may be backdated to a provider timestamp. The operational gate also requires proven `processed_at`. |
| `version_id`, `revision_rank` | Require documented amendment identity and source ordering, including equal-time ties. A payload hash identifies bytes but does not establish provider revision order; no timestamp/row-number ranking is approved. |
| `source_uri`, `license_id`, checksum | Preserve the exact credential-free request identity, reference the applicable rights evidence, and SHA-256 the exact acquired representation. Retain transport/encoding metadata separately; decoded/re-encoded rows must not masquerade as original response bytes. |

`RawAvailability.event_at` accepts only a datetime or `None`; a date-only event
must remain in the original payload/evidence, with that envelope field unknown.
The release-claim type can separately preserve a date as a date.

`ts_effective` filters economic/effective history; the API defaults to that index
and also permits `ts_record`. Neither filter is documented here as an independent
public/provider-release cutoff. The product page also disagrees on cadence:
its header says weekly while its FAQ says four daily publication windows.
Do not infer exact availability from either schedule or a fixed lag.
[Range API](https://databento.com/docs/api-reference-data/security-master/security-master-get-range?lang=python),
[product page](https://databento.com/security-master).

**Current disposition:** historical replay is blocked by missing release and
revision evidence. Prospective capture would record when we received bytes, but
would not repair missing public-release proof or establish earlier knowledge.
Even a syntactically accepted receipt does not authenticate these assertions.

## Revisions, completeness and delistings

The API returns listing-level records within a requested range. It permits
security-ID queries and allocation-limited requests that can omit rows. A
successful response is therefore insufficient evidence of complete history.
[Range API](https://databento.com/docs/api-reference-data/security-master/security-master-get-range?lang=python).

Before constructing `ListingHistory`, prove the entire replacement assertion for
one security/source, across all its venues and intervals. A U.S./venue/date filter,
plan limit, missing predecessor state or truncated response must not silently
erase other intervals. Keep pilot selection separate from history acquisition.
Do not interpret an empty response as delisting, an empty replacement, or proof
of absence. These follow [ADR 0007](../decisions/0007-historical-security-listings.md).

There is also an interface mismatch: the provider can group distinct listings
in different currencies on one exchange. Our `ListingHistory` rejects overlapping
intervals for the same security/venue regardless of currency. Qualify a pilot
whose complete histories fit that constraint or propose a separately reviewed
contract change. Never collapse those listings, use `listing_id` as a security ID,
or invent venue codes to bypass validation.
[Provider field scopes](https://databento.com/docs/schemas/security-master),
[current validation](../../src/quant_test/data/listings.py).

Unresolved questions are whether old assertions remain retrievable after
correction, how changed/deleted rows and equal-time amendments are identified,
and whether retrospective changes carry their own release evidence. Do not
overwrite earlier payloads, merge deltas into an invented complete history, or
use an empty history to simulate a retraction. `ObservationVersion` rejects
retractions; handling them needs a separate reviewed contract. Preserve ended
listings and source-defined end reasons, while requiring evidence for their
exact boundaries and meanings. Listing absence never implies universe removal.

## Acceptance evidence and next step

The next task is to resolve the following qualification questions using an
applicable agreement and authoritative provider evidence; this document does
not authorize contacting the vendor or buying access:

1. What exact per-version fields/evidence establish public release and actual
   customer availability, including backfilled and corrected records?
2. What are ID persistence/reuse rules, amendment identities, ties, deletions and
   historical revision retention guarantees?
3. How can a request prove complete multi-venue history without entitlement,
   range, allocation or delivery omissions? What pilot coverage gaps exist?
4. What instant semantics apply to listing status transitions, and what original
   precision is available? Which native symbols are unambiguous, and can complete
   pilot histories fit the existing same-security/venue overlap constraint?
5. Does the owner's agreement permit archival replay, post-termination retention,
   chosen identifiers and a small fixture shared with reviewers/CI?

Once acquisition is authorized and these answers support a meaningful slice,
obtain the smallest permitted real sample covering a rename, delisting/relisting,
late correction and ambiguous/missing case. Archive the exact response, request
scope, acquisition timestamp, checksum and rights/evidence references. Keep
licensed bytes in ignored `/data/`; only publish fixtures with explicit rights.
An independent reviewer must derive expected identities and temporal boundaries
from source evidence. The existing hand-specified tests are not vendor fixtures.

A subsequent adapter PR must demonstrate:

- Unknown/date-only/unproven release claims remain quarantined with original
  precision and reasons; no date or ingestion time fills a release field.
- A correction becomes eligible only after both proven release cutoffs, without
  changing earlier decisions; ambiguous ranks and unsupported retractions fail.
- Stable IDs survive ticker reuse, ended listings stay queryable, and truncated
  histories never become replacements. Universe joins retain unresolved members.
- Receipts reopen with identical assertions and verified bytes; corrupt/missing
  selected payloads fail without fallback, and counts describe receipt identities.

No candidate has passed these gates. Until the rights and temporal/identity/scope
evidence is supplied, the deliverable is this proposed qualification record;
validated ingestion remains blocked. All external citations above were reviewed
on 2026-11-10 and can change; preserve approved evidence when a source is adopted.
