# ADR 0013: Explicit immutable version-catalog inventories

- **Status:** Proposed for M1 review
- **Date:** 2026-11-10

## Context

ADR 0012 retains one explicit observation-version assertion and its verified raw
receipt linkage. Reconstructing a historical selector still requires an explicit
collection of those metadata digests. Scanning an archive would mix unrequested
objects, and checking records individually cannot detect conflicting version IDs,
ranks or revision availability within an observation key.

## Decision

`data.catalog_inventories.VersionCatalogManifest` pins an explicit built-in tuple
or list of distinct lowercase observation-record SHA-256 digests. Invalid
containers, entries and duplicate digests reject before archive reads. Input is
copied into a sorted immutable tuple. Empty inventories are explicit and valid;
they make no claim about unmentioned records or real-world coverage.

`build_version_catalog_inventory(archive, observation_record_sha256s)` requires a
`LocalRawArchive`, including for an empty inventory. It reopens every selected
record through `get_observation_record`, verifying metadata, accepted receipt,
payload and shared-field linkage. It constructs a frozen `VersionCatalogInventory`
with the manifest and records in manifest digest order. Each record's canonical
metadata digest must equal the corresponding manifest digest. All versions are
validated together by the existing `VersionCatalog`: duplicate version IDs or
ranks within a key and availability order contradicting rank reject. No records
are merged because they share a receipt or payload. Key/source partitions and
equal-availability rank tie-breaking remain unchanged.

`inventory.to_catalog()` returns a fresh `VersionCatalog` over the immutable
records. Historical selection uses the existing inclusive public/provider cutoff
and ignores later backfill ingestion. The inventory retains record/receipt
provenance independently of the selector. Direct inventory construction validates
shape, digest correspondence and catalog consistency, not existing dependencies
or external source truth.

Schema version 1 is canonical ASCII JSON with sorted object keys, compact
separators, escaped non-ASCII and no trailing newline. It contains only
`schema_version`, `catalog_policy_id="observation-version-catalog-v1"`, and
`manifest={"observation_record_sha256s":[...]}`. Observation records remain
separate dependencies. The literal independent fixture
`tests/fixtures/version-catalog-inventory-v1.json` pins exact bytes/schema.
`encode_version_catalog_inventory` serializes an inventory assertion without
accessing an archive. `decode_version_catalog_inventory(payload, archive)` rejects
duplicate/unknown/missing fields, unsupported schema/policy/types, duplicate or
unsorted membership and noncanonical bytes. It reloads every dependency,
revalidates catalog rules and requires exact canonical byte equality.
Changes to these consistency/selection semantics require an explicit policy
version decision; old inventories must not be silently reinterpreted.

`LocalRawArchive.put_version_catalog_inventory(observation_record_sha256s) -> str`
verifies every dependency and catalog invariant before publishing one canonical
manifest object last under its separate digest. It creates no observation record,
receipt or payload. `get_version_catalog_inventory(digest)` verifies that exact
manifest and all dependencies before returning. Callers retain the digest; there
is no global index, discovery or implicit inclusion.

## Failures and limits

Invalid arguments or catalog contradictions raise `ValueError`; standalone
decoding wraps malformed or inconsistent inventories as
`VersionCatalogInventoryFormatError`, a `ValueError` subtype.
`VersionCatalogInventoryMissingError` and `VersionCatalogInventoryCorruptError`
inherit `RawArchiveError`. Observation-record, receipt, payload and filesystem
failures retain their original types. Any dependency failure prevents success;
there is no partial inventory, fallback, member removal or repair.

Existing ADR 0009 publication/failure assumptions apply: a trusted local POSIX
root, verified no-replace publication and no fsync/crash-durability guarantee.
Pre-publication failure exposes no new manifest. Cleanup or directory-close
failure can raise after a complete manifest is linked; retry verifies it without
removing abandoned staging files. Existing complete content is never overwritten.
Put retains the base publication error types; dedicated missing/corrupt errors
describe inventory loads.

This inventory persists a selected collection of explicit metadata assertions.
It does not authenticate source evidence, revision semantics, identity, license or
coverage; receipt acceptance still does not promote a version. It carries no
decision/query cutoff, effective listing scope, code/config/environment pins,
transform lineage, quality/completeness report or processing evidence. It is not
an evaluable dataset snapshot. Listing/membership persistence, provider ingestion,
financial/trading behavior and services/dependencies are outside this slice. All
M1 gates remain open.

## Reference evidence

Tests must pin independent literal bytes/hash and cover explicit empty membership,
invalid archive even when empty, pre-read validation, input snapshots and order,
manifest/record correspondence, duplicate IDs/ranks and contradictory revisions.
Independent temporal cases exercise exact release boundaries, rank ties,
key/source isolation and historical backfills after reopen. Missing/corrupt
manifests or any dependency fail; strict rehashed schema/policy/type/membership
tampering, nested duplicate keys and noncanonical bytes reject. Injected
dependency, pre-link and post-link failures preserve existing archive semantics.
Local checks do not prove remote CI, independent approval or source readiness.

## Alternatives

Directory discovery would silently include unrequested artifacts. Deduplicating by
payload or receipt would erase distinct assertions and hide identity conflicts.
Embedding records duplicates the existing content-addressed dependency graph;
mutable indexes introduce update/recovery requirements. An explicit immutable
manifest reuses the narrow storage boundary while retaining existing selector
semantics and leaving decision-time dataset artifacts to separate slices.
