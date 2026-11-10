# ADR 0019: Offline replay of the locked development toolchain

- **Status:** Proposed technical design; implementation under review
- **Date:** 2026-11-10

## Context and bounded outcome

[ADR 0003](0003-reproducible-environments.md) already requires an unseeded,
hash-verified development environment and retained distributions for offline
replay. The existing `scripts/verify_hash_install.py` verifies the local package
wheel, including wrong-hash rejection when that version is already installed.
It does not replay all locked development distributions.

One additive development verifier will preflight an explicit platform-specific
wheelhouse, publish canonical manifest bytes identifying its actual inputs, then
immediately reopen that manifest and use those inputs to create a fresh offline
environment and run the repository's actual installed-package test suite. This
is a consumer of retained wheel bytes, not another standalone assertion format.

Preserve the existing verifier's CLI, behavior and same-version negative hash
check. No new package, GitHub Action, service, financial convention, runtime
environment manager or storage backend is proposed. `packaging` is already
hash-locked development tooling; its public requirement/marker/wheel/tag APIs
may be used by this development script, without adding a runtime dependency.
Observe and require host pip and packaging versions to equal their active locked
versions and record them. Version equality alone does not recover or authenticate
the host distributions' original wheel bytes.

The result is a **toolchain replay report**, not the complete experiment
environment manifest required by [environment.md](../environment.md#required-run-manifest-before-m3-implementation-is-complete).
It authenticates neither sources nor experiments. It needs no market-data
entitlement, user dataset, account or credentials.

## Proposed additive command boundary

`scripts/verify_toolchain_replay.py` has two explicit subcommands:

```text
capture --wheelhouse ABS_DIR --local-wheel ABS_WHEEL --lock ABS_LOCK
        --expected-lock-sha256 HEX --expected-local-wheel-sha256 HEX
        --source-root ABS_REPO --report-dir ABS_EXISTING_DIR

replay  --manifest-sha256 HEX --report-dir ABS_EXISTING_DIR
        --wheelhouse ABS_DIR --local-wheel ABS_WHEEL --lock ABS_LOCK
        --source-root ABS_REPO
```

`capture` validates and publishes only the input manifest, returning its SHA-256.
`replay` reopens and revalidates everything, performs the offline consumer and
publishes a separate success report only after all checks pass. CI must invoke
both; capture alone is never acceptance. There is no arbitrary shell command,
alternate index, environment path or executable embedded in the manifest.

Require the running interpreter to match `.python-version` and the observed uv
version to be 0.13.5. The verifier uses that actual interpreter to create its
child environment, not a version that uv might download. Record actual build and
platform observations. Supported acceptance platforms remain Ubuntu 24.04 and
macOS 15; OS names alone do not pin an immutable machine image.

The explicit expected hashes are caller trust inputs for capture, usually
computed immediately after CI materialization/build. They detect substitution
between that step and capture; they are not an independent signature of a build.
Replay pins both files through the manifest and requires exact byte hashes.
The supplied lock must also equal the checked source root's
`requirements-dev.lock` bytes; a relocated identical copy is valid. Different
lock choices require a different clean source revision. This is correspondence,
not authentication that the financial/source/toolchain choices were reviewed.

## Materialization: networked and separate

Keep the already approved initial CI bootstrap/install and local-wheel build.
After the lock-installed pip exists, use it to download the full lock into a new,
empty wheelhouse for the current interpreter/platform. Do not request another
platform, interpreter, ABI or implementation. Do not use `--no-deps`, upgrades,
source archives or unpinned requirements.

The following argv shape was checked against the installed pip 26.3 help:

```text
<baseline-python> -I -m pip --isolated --disable-pip-version-check --no-input
  download --require-hashes --only-binary=:all: --no-cache-dir
  --keyring-provider disabled --index-url https://pypi.org/simple
  --dest <new-empty-wheelhouse> -r <absolute-requirements-dev.lock>
```

Pass `PIP_CONFIG_FILE=os.devnull` in the controlled child environment as well as
`--isolated`, plus `NETRC=os.devnull` so requests cannot obtain ambient netrc
credentials; disabled keyring alone does not suppress netrc. pip 26.3's installed
configuration source confirms the config setting suppresses
all configuration files, whereas `--isolated` alone names user configuration.
Remove ambient `PIP_*`, `UV_*`, `PYTHONPATH`, `PYTHONHOME`, pytest option/plugin
variables and proxy/index credential variables before adding the few deliberate
settings. Preserve normal system paths rather than redefining a home directory.
Disable credential/keyring lookup; do not dump configuration or environment values.

The script's fixed `download_locked_wheels(lock, destination)` helper performs
this separate operation with strict lock/pinned-host-tool validation before pip;
the destination must be an exclusive new directory. It offers no index/command
configuration. The [environment instructions](../environment.md#full-locked-toolchain-offline-replay)
and CI show its explicit invocation. The local package wheel stays outside it.

This download is intentionally networked. It obtains the already locked
development dependencies from the explicit public index and checks their hashes.
Its success is not evidence that the later replay phase needed the network.
Download failure or an unavailable compatible wheel fails the slice; do not
resolve a replacement, source-build it or pretend a placeholder wheel completes
the wheelhouse.

The existing local source build remains a separate explicit operation using the
locked backend with `--no-deps --no-build-isolation`; no third-party source build
is added. Keep its local wheel outside the dependency-only wheelhouse. Preserve
the original local-wheel hash acceptance check.

## Preflight and strict lock subset

Use a trusted local POSIX root model, consistent with [ADR 0009](0009-local-raw-payload-archive.md).
Callers must exclude hostile/concurrent mutation during capture/replay. Reject
symlink path components, `..`, missing/nonregular files and non-directory roots
for lock, wheelhouse, local wheel, report root and source inputs. Use no-follow,
nonblocking regular-file reads for artifact bytes so FIFOs cannot block.
Runtime virtual-environment interpreter symlinks are a distinct bootstrap detail,
not a permitted wheel/lock symlink input; record the actual interpreter target.

Inspect only direct wheelhouse children. Require safe ASCII wheel basenames with
no separators/control characters; parse using `packaging.utils.parse_wheel_filename`.
Reject directories, links, sources, nested content, unexpected files and duplicate
canonical distribution names, even if versions or hashes differ. Exactly one
compatible wheel per active locked distribution is allowed. The local project
wheel must not also appear in the dependency wheelhouse.

Parse only the repository's reviewed generated-lock subset: comments/blank lines,
backslash continuations, one named exact `==` version with optional PEP 508 marker,
and one or more lowercase SHA-256 `--hash` values. Reject wildcards, ranges,
extras, URLs, paths, editables, includes/constraints, index options, arbitrary
directives and ambiguous duplicate active names before invoking an installer.
Unsupported future lock syntax requires an explicit design update, not silent
interpretation. Evaluate markers with the running baseline interpreter's explicit
`packaging.markers.default_environment()`; persist this nonsecret marker mapping.
The current lock has a Windows-only colorama entry which must not enter either
supported-platform wheelhouse, and a CPython-active librt entry which must enter.

For every active requirement, independently require:

1. Exactly one wheel whose canonical name/version matches the active lock entry.
2. Its exact byte digest belongs to that entry's allowed lock hashes.
3. Its parsed tags intersect the current interpreter's supported tags.
4. Its wheel metadata is readable without executing/extracting code, with one
   matching top-level distribution METADATA/WHEEL identity (nested vendored
   metadata remains hash-pinned package data, not another installed distribution);
   reject malformed ZIP/member or
   filename/metadata identity contradictions. WHEEL Tag metadata must equal the
   parsed filename tags, not merely be compatible with the interpreter. Check
   Requires-Python compatibility.

Require equality between wheelhouse names and the full active-lock name set;
never accept a subset just because a package import happens to succeed. Validate
all supplied artifacts before creating the replay environment. Verify the local
wheel's expected digest, compatible tags and metadata identity/version against
the repository project metadata. Its hash is separately pinned, not claimed to
be in the dependency lock. This does not cryptographically prove which source
produced that wheel.

`--source-root` is an explicit trusted checkout for the suite. Require its actual
Git revision and clean tracked/untracked status with read-only Git checks
(`GIT_OPTIONAL_LOCKS=0`); reject dirty input in this first
slice rather than claiming to retain an exploratory patch. Record the observed
commit and recheck revision/status after the consumer. Standard ignored build/
cache files are not a claim of a complete filesystem snapshot. No source hash
provided as a plain string is treated as verified merely because it is supplied.

## Immutable manifest and immediate read-back

Schema 1 uses canonical ASCII JSON: sorted object keys, compact separators,
escaped non-ASCII, no trailing newline; exact field sets/types and duplicate-key
rejection. All SHA-256 values are lowercase 64-character hex. Collections use
canonical distribution-name order. Exclude wall-clock times, temporary absolute
paths, download URLs and environment dumps from identity.

The input manifest contains only:

- `schema_version=1`, `policy_id="offline-locked-toolchain-replay-v1"`.
- Actual lock byte SHA-256; ordered active requirements `(name, exact version)`.
- For each selected dependency wheel: safe basename, canonical name, version,
  actual size and exact byte SHA-256. The original lock remains a required input.
- Separate local-wheel basename/name/version/size/hash.
- Observed Python implementation/version/build/cache tag, resolved interpreter
  target file SHA-256, `platform.system/release/version/machine`, explicit marker
  environment, observed host pip/packaging versions and actual uv version. Hash the uv executable too if it is directly
  readable; absence of readable executable provenance must be an explicit
  limitation, never a fabricated digest. Do not claim these hashes identify all
  interpreter/native libraries or an OS image.
- Observed clean repository commit; fixed consumer policy identifying the actual
  repository suite and import-origin checks below.

Reuse existing `LocalRawArchive` only as the existing exact-byte publication
mechanism in the explicitly owned report directory: encode/hash, publish without
replacement, reopen and require exact canonical bytes. No new backend or generic
artifact framework is needed. Its no-fsync, no-crash-durability, post-link cleanup
failure and retry limits remain. Canonical data objects can be held in frozen
development-only types; no new public platform snapshot contract is implied.

Replay receives the expected manifest digest externally, reopens it, recomputes
the active plan from the supplied lock/current interpreter, rechecks every input
byte and requires exact manifest correspondence. A rehashed changed manifest is
a new assertion; a hash is not owner/source authentication. Platform/interpreter
mismatch rejects rather than attempting cross-platform replay.

## Offline environment and real consumer

After successful read-back/preflight, create one task-owned temporary environment.
Resolve the pinned uv executable explicitly, invoke subprocesses with argv arrays
and controlled environment, and never execute strings through a shell. The
following flags were verified in installed uv 0.13.5 help:

```text
uv venv --offline --no-cache --no-config --no-project
  --no-python-downloads --python <actual-baseline-executable> <new-venv>
```

Do not pass `--seed`, `--system-site-packages`, `--allow-existing` or `--clear`.
For every child Python metadata/import/consumer probe, use isolated mode (`-I`)
from an unrelated task-owned temporary working directory, including the initial
empty-environment and final inventory probes. Repository-local egg-info can
otherwise appear alongside installed metadata and falsely look like a duplicate
distribution; do not repair that by deduplicating the inventory. Explicitly inspect
child `importlib.metadata.distributions()` before installation and require it to
be empty. Clear ambient settings such as `UV_VENV_SEED` so
omitted flags cannot be overridden. Nothing supplied by a caller chooses an
existing destination environment.

Copy the verified regular input bytes into a task-owned staging wheel directory,
read them back and verify hashes again. Install using a generated, deterministic
requirements plan of the exact staged local wheel paths and selected hashes,
one entry for each active locked distribution plus the project wheel. All
dependency entries were already checked against the original lock. Exact paths
remove candidate selection ambiguity; manifest identity remains relocatable.

```text
uv pip install --python <new-venv-python>
  --offline --no-index --no-cache --no-config --no-python-downloads
  --no-build --only-binary=:all: --require-hashes --reinstall --strict
  -r <generated-exact-wheel-plan>
```

These flags do not constitute a hostile-code network sandbox. They disable
installer network resolution/downloads/builds. The local project/wheels/tests are
trusted reviewed code; arbitrary installed code could otherwise open sockets.
No hostile-wheel execution or network-sandbox guarantee is claimed.

Use the fresh child interpreter to require exactly the active lock inventory
plus the local project: canonical name/version equality, no duplicate normalized
names, no additional distributions or editables. Run `pip check` there. The claim
about consumed wheel hashes comes from the controlled installation just performed,
not from a post-hoc version scan of an unrelated environment.

Then, from an unrelated task temporary working directory:

1. With Python isolated mode, import `quant_test` and required modules; verify
   their origins are under this fresh environment's installed site-packages,
   outside repository `src` and the host environment. Reject editable/direct
   source fallback.
2. Run the actual repository suite with the child Python in isolated mode and
   pytest's verified `--import-mode=importlib`, using the explicit repository
   config and tests path. No `PYTHONPATH` or source-directory insertion. A junit
   output in task scratch space can record actual collected/pass/failure counts;
   zero collected tests is not success.
3. Recheck installed inventory, artifact hashes and source revision/clean status
   after the consumer, requiring unchanged input identities. Failure yields no
   success report.

Do not recursively invoke this full positive consumer from a test in that same
suite. Pure/preflight negative tests may be in pytest; the real complete positive
case is the explicit CI verifier invocation. This prevents recursive test runs.

Publish canonical success-report bytes last through the same existing archive.
The report pins input-manifest digest, actual installed inventory, observed child
interpreter/platform, exact fixed consumer argv policy, actual return codes and
test counts. Capture stdout/stderr for diagnostics without printing unrestricted
environment/configuration or credentials. A failed process must remain failure;
do not invent successful counts or publish a report with `passed=true` on error.

## Tests and actual acceptance evidence

| Boundary | Required evidence |
| --- | --- |
| Parser/identity | Independent literal canonical manifest bytes/hash; active/inactive marker cases; exact versions/hashes; duplicate active requirements; unsafe paths/basenames; malformed/duplicate/noncanonical JSON; unsupported lock syntax rejects. |
| Whole wheelhouse | Missing active wheel, extra wheel, two wheels for one canonical name, sdist/nonregular/symlink/FIFO, incompatible tag or metadata contradiction rejects before installation. Unit ZIP fixtures test parsing only, never establish real lock completeness. |
| Direct lock mismatch | After capture, change any lock byte: replay fails pinned lock digest before install. Independently change a required allowed hash and supply the new expected lock digest: actual unchanged wheel must fail allowed-hash membership. |
| Direct local-wheel mismatch | Change local wheel bytes after expected hash/capture: fail pinned digest before install. Wrong project/version or incompatible local wheel rejects even with a correctly recomputed supplied hash. |
| Artifact change | Corrupt selected wheel bytes, alter file after capture, or change staged bytes: no repair/fallback/install. Test missing/corrupt manifest and publication read-back failures. |
| Bootstrap/process failure | Unexpected uv/Python version, seeded child inventory, subprocess nonzero, inventory extras/mismatch, source import fallback, test failure/zero collection and input mutation reject without success report. Process doubles verify sequencing only, not real replay success. |
| Actual complete consumer | On both configured CI platforms, materialize real compatible hash-verified locked wheels and real built project wheel; capture/read back; offline install into empty child; exact inventory and `pip check`; actual installed suite passes. Record literal checked-out SHA, run URL/platforms, lock and selected wheel hashes, manifest/report digests and actual test counts. |
| Existing regression contract | Preserve and execute `python scripts/verify_hash_install.py <built-wheel>`, including wrong hash rejection for the already installed same version and valid reinstall. |

The implementation still runs all four required repository quality checks and
independent review. CI should retain its present checks and append materialize +
capture + replay to the existing jobs using existing actions. No upload action or
dependency is introduced; do not broaden permissions. A rerun need not repeat
unrelated checks beyond ordinary CI unless a new failure/change requires it.

## Limits and evidence status

Runner-local wheelhouse/manifest/report files are ordinary ephemeral files. No
CI upload, durable retention, disaster recovery or future download availability is
claimed. Logs may identify bytes without retaining them. Future replay requires
the actual wheels/lock/local wheel and matching bootstrap environment to remain
available; a report digest cannot recreate missing bytes.

This records a controlled new installation, not historical distribution bytes of
the host environment. Interpreter, uv/action binaries, index availability and
runner images remain explicit bootstrap trust inputs. It pins no immutable OS
image and promises no cross-platform bitwise equality. It does not collect full
native-library/OS provenance, dirty-run patches, source datasets, models,
configuration/seeds, numerical/thread settings, performance tolerances, holdout
ownership or an experiment result. All broader M1/M2/M3 gates remain open.

The implementation includes strict/preflight/process-negative references and
an explicit CI consumer recipe. Actual complete positive acceptance requires a
clean committed source revision and real dependency/local wheel bytes; this ADR
records no successful remote run, complete experiment manifest or milestone
approval. Local unit fixtures/doubles establish only their stated mechanics.
