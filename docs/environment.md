# Reproducible execution environment

## Supported baseline and installation
The reproducibility baseline is CPython 3.11.17, pinned in `.python-version`. CI is configured for Ubuntu 24.04 and macOS 15. Other interpreters allowed by package metadata and other platforms are not verified environments. Runner images can change; a run must record its actual OS/image and interpreter build. A pinned dependency lock is not a claim of bitwise reproducibility across operating systems.

Use a fresh, unseeded virtual environment with the exact baseline interpreter. Follow the [README installation commands](../README.md#local-development). `requirements-dev.lock` pins direct/transitive development dependencies and pip/build tooling with distribution SHA-256 hashes. Use uv 0.13.5 to install it with `--require-hashes --only-binary=:all: --reinstall`; unsupported wheel/platform combinations fail instead of introducing unrecorded source builds. `--reinstall` prevents an already installed matching version from bypassing distribution hash verification. Do not seed pip/setuptools/wheel before this step: these packages must enter the environment through the verified lock. Install this repository afterward with `--no-deps --no-build-isolation` so its build uses the locked backend. `pip check` must pass. No runtime dependency is added by this policy.

An existing environment may contain extra packages even after installation; recreate it rather than treating an in-place update as a clean replay. Offline replay requires a retained wheelhouse of the exact hash-verified distributions and the matching interpreter/OS environment. Hash verification does not replace license or security review.

## Updating the lock
`pyproject.toml` remains the declared package/dev dependency contract. `requirements-toolchain.in` declares installer/build tooling and must remain compatible with `[build-system].requires`. The lock was generated with uv 0.13.5, a development-only tool. CI uses the same pinned uv version to install managed CPython 3.11.17 on both platforms and install the hash-locked dependencies into an unseeded environment; the verified pip then builds/installs the local package. The pinned installer action is recorded in the workflow. This avoids downgrading macOS to an older Python patch: GitHub's setup-python manifest has no macOS 3.11.17 build. Local setup uses the same uv version and commands. No runtime package manager is added. See [ADR 0003](decisions/0003-reproducible-environments.md).

For an intentional refresh, use the recorded resolver version and run from the repository root:

```bash
uv pip compile pyproject.toml requirements-toolchain.in --extra dev --python-version 3.11 --universal --generate-hashes --upgrade --output-file requirements-dev.lock
```

Review every direct/transitive change and its licensing/security implications. Commit input, lock, and rationale together. Install into a fresh environment, run `pip check` and all four quality checks, and obtain CI evidence on both configured platforms before declaring a refresh verified. Do not edit distribution hashes by hand or resolve newer versions while replaying an experiment. A new dependency still requires the rationale/ADR and review required by repository policy.

## Offline hash-verification acceptance check
After installing the locked environment, run:

```bash
python -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir dist .
python scripts/verify_hash_install.py dist/quant_test-0.1.0-py3-none-any.whl
```

The check uses the actual dependency-free repository wheel and a temporary unseeded environment. With network access and caches disabled, it verifies that the environment initially contains no distributions, installs the wheel with its computed SHA-256, attempts the same installed version with an invalid hash and requires a hash-mismatch failure, then reinstalls successfully with the correct hash. This checks installer behavior at the prior bypass boundary; it does not claim the local package's source is authenticated by the third-party lock. CI runs this check on both supported platforms after building the wheel.

## Required run manifest (before M3 implementation is complete)
Each experiment must retain an immutable environment manifest and checksum alongside its result. Record:
- Python implementation, exact version/build, executable provenance, OS/image or container digest if used, architecture, and relevant native numerical-library versions.
- `requirements-dev.lock` checksum plus the actual resolved distributions/versions and distribution hashes or retained wheelhouse manifest. Record the installer/build-backend versions and the local package source revision; `pip freeze` alone does not identify distribution bytes.
- Repository revision and clean-tree status; an exploratory dirty run must preserve the patch/hash and cannot serve as promotion evidence until reproduced from a clean revision.
- Configuration, data/source snapshot, transform/model artifact, and seed identifiers. Record RNG/library versions, timezone, locale, numeric precision settings, and relevant thread/determinism settings without copying credentials or unrestricted environment variables.
- Replay command, environment manifest version, and limitations such as nondeterministic kernels or platform-specific floating-point differences. Define exact equality or a justified reference tolerance before comparing results; a seed does not guarantee identical computation.

For local inspection, `python -VV`, `python -m pip inspect --local`, `python -m pip freeze --all`, and `python -m pip hash requirements-dev.lock` supply parts of this evidence. The experiment registry must combine them with the remaining provenance when implemented. No experiment runner or manifest collector is claimed to exist in the scaffold.
