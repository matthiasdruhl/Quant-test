# ADR 0002: Historical and operational information eligibility

- **Status:** Accepted for the timestamp primitive; ingestion and derived-lineage enforcement remain milestone work
- **Date:** 2026-11-09

## Context
Historical source replay must allow today's backfill of a fact proven available in the past. An operational decision additionally requires evidence that the platform received and processed that version. Treating either interpretation as universal either excludes valid historical evidence or admits information the running system never had. An unknown event time does not establish an unknown publication time, and vice versa.

## Decision and compatibility
Keep `InformationAvailability.first_usable_at` and `is_usable_at` as historical source checks, using the inclusive maximum of publication/provider release. Existing calls with aware datetimes retain their result. Widen `event_at` to `datetime | None`; a missing event is preserved without inventing a timestamp. Publication, provider availability, and ingestion remain required aware datetimes. Invalid runtime values raise `ValueError` rather than leaking an attribute error. No constructor argument is removed or reordered.

Normalize comparisons and `first_usable_at` to UTC while preserving the original record fields. This corrects ambiguous daylight-saving fallback comparisons: same-zone Python datetimes can otherwise compare wall clocks even when `fold` denotes different instants. Callers must treat the property's timezone representation as UTC; ordinary aware-datetime instant comparisons remain compatible. A previously premature/late DST eligibility result intentionally changes to the correct instant.

Add `is_available_to_platform_at(decision_at, *, processed_at)` as an explicit operational information check. Processing completion must be timezone aware and no earlier than ingestion. Eligibility requires the maximum of public release, provider release, ingestion, and processing no later than decision time. There is deliberately no default processing time and no implicit mode switch in the historical method.

Raw observations with uncertain public/provider availability remain outside this validated type and ineligible until source evidence establishes exact release times. Adapters must preserve the missing/uncertainty reason and evidence; the primitive cannot verify claims. Derived/model lineage is an additional validation layer defined in the data contracts, not inferred from one record's timestamps.

## Reference cases and consequences
- Public 12:00, provider 14:00, ingestion 18:00, processing 19:00: historical eligibility begins at 14:00; actual platform eligibility begins at 19:00, including equality.
- Public 20:00, provider 12:00, ingestion 18:00, processing 19:00: both checks still wait until public release at 20:00.
- Unknown event time with proven public/provider release uses those releases. Missing public/provider release rejects construction. Processing before ingestion rejects the operational check.
- Offset-aware times compare by instant, including the repeated DST hour; naive times reject both checks.

The unit suite implements these reference/negative cases. The change introduces no storage, broker access, dependency, or accounting convention. Future paper adapters must enforce the operational check; adding this method alone does not implement those adapters or authorize execution.

## Alternatives
Using ingestion for every mode corrupts backfilled historical replay. Ignoring ingestion for every mode permits unseen operational inputs. A defaulted mode argument would silently select the wrong policy for existing callers, so separate explicit methods preserve compatibility.
