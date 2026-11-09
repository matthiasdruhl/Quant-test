# ADR 0009: Exact-byte local raw payload archive

- **Status:** Proposed for M1 review
- **Date:** 2026-11-09

## Context

`ObservationVersion.content_sha256` identifies content stored elsewhere, but the
existing in-memory catalogs cannot retain or verify that content. Replaying a
selected revision requires its exact bytes. Substituting an older payload when
the selected one is missing or corrupt would silently change the research input.
A local byte archive is a narrow storage boundary before provider ingestion,
metadata persistence, and reproducible dataset manifests.

## Decision

`data.raw_archive.LocalRawArchive` stores opaque immutable `bytes` in an existing
local directory. The constructor requires an absolute `pathlib.Path` without
`..` components; the directory and all its ancestors must exist without symlink
components. It does not create directories. The caller owns the root, its access
permissions, and capacity. This standard-library implementation adds no
dependency, service, database, or financial convention.

The only object key is an exact lowercase 64-character SHA-256 hexadecimal digest.
Each object is a regular file named by that digest directly under the root.
`put(content_sha256, payload)` verifies the digest of the supplied bytes before
any write. `get(content_sha256)` verifies the complete file before returning bytes.
Empty and binary content are valid; no decoding, decompression, normalization,
canonical serialization, metadata injection, or timestamp transformation occurs.
Adapters must define which exact source byte representation their version hashes.

A new put writes an exclusively created random `.staging-*` file in the same
directory, handles short writes, removes write permission, closes it, and reads
it back to verify both its digest and equality with the supplied bytes. A hard
link then publishes the final digest name without replacing an existing object;
the staging name is removed in a `finally` block. Readers see no final object
until a complete staged file is linked. Existing objects, including an object
published by a competing writer, must verify and equal the supplied bytes before
an idempotent put succeeds. Corrupt objects are never overwritten or repaired.
The API exposes no update, delete, listing, or automatic cleanup operation.

The supported environment is a trusted local POSIX filesystem with directory
file descriptors, no-follow opens, and atomic no-replace hard links. Cooperating
writers can publish the same digest; callers must exclude hostile mutation,
replacement, deletion, or in-place writes to the root and its objects. Symlink,
directory, and FIFO objects at digest names reject. Read-only object permissions
are an accidental-write safeguard, not tamperproof storage or an access-control
boundary. This is not a network/object-store backend or a secure sandbox.

No file or directory `fsync` is performed. Successful return establishes byte
verification and publication in the running filesystem, not process/power-failure
durability. Abrupt termination may leave staging files or lose published data.
An operator must assess and remove abandoned staging files while writers are
stopped; no recovery/garbage-collection protocol is implemented.

## API and failures

- `put(content_sha256: str, payload: bytes) -> None` and
  `get(content_sha256: str) -> bytes` address exact content.
- `put_version(version: ObservationVersion, payload: bytes) -> None` and
  `get_version(version: ObservationVersion) -> bytes` use exactly that version's
  checksum, without changing or persisting the version.
- Invalid digest, root, payload, or version argument types/values raise
  `ValueError`. Payloads must be `bytes`, not mutable buffers or text.
- `PayloadDigestMismatchError` rejects supplied bytes before creating a file.
  `PayloadMissingError` identifies an absent requested object.
  `PayloadCorruptError` identifies a nonregular or checksum-invalid object, or
  unequal bytes despite matching digests. All inherit `RawArchiveError`.
- `ArchiveIOError`, also a `RawArchiveError`, wraps filesystem failures and retains
  their cause. It does not imply that publication failed: cleanup can fail after
  a complete final object has been published. Retrying the same put verifies an
  existing object before succeeding; it does not remove abandoned staging files.

Consumers first select the historically eligible `ObservationVersion` with the
existing catalog, then fetch exactly its checksum. A missing/corrupt selected
payload fails explicitly and must never initiate fallback to a different revision.
The archive itself has no decision cutoff or eligibility check. Storing or reading
bytes establishes neither historical availability nor completed operational
processing, source authenticity, license rights, identity, or revision order.
Identical content may share a checksum across different version/source records;
the archive does not bind content to provenance or isolate licenses/access rights.

## Scope and evidence

Only payload bytes persist. Observation metadata, evidence references, raw
availability envelopes, admission/quarantine results, revision indexes, coverage
reports, and dataset manifests remain unpersisted. No provider adapter, network
access, OHLCV, corporate actions, strategy, deployment, account creation, or trading
path is added. Existing temporal/public contracts are unchanged; all M1 gates
remain open for complete CI, independent review, and owner acceptance evidence.

Contract tests use the independently specified SHA-256 `abc` and empty-byte test
vectors plus hand-specified binary bytes and revision cutoffs. They cover reopen
and idempotency, mismatch before write, corrupt/missing payloads, invalid paths
and arguments, symlinks/nonregular files, short/failed/zero-progress writes,
staging verification, competing publication, cleanup failures, and read failures.
A late correction reference selects metadata before access and requires missing
or corrupt selected content to fail without fallback, despite a readable older
revision and later historical backfill ingestion. Injected faults are deterministic
tests, not evidence of crash durability, real concurrent stress, provider coverage,
remote CI, or independent approval.

## Alternatives

Overwriting a digest path could conceal corruption or expose partial writes.
`os.replace` provides replacement semantics that violate the no-replace contract.
A database or external object service would expand this slice without a current
need. Canonical serialization would define new source representations; retaining
exact adapter-supplied bytes keeps that decision explicit and separate.
