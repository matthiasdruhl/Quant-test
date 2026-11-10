# ADR 0003: Hash-locked development and replay environments

- **Status:** Accepted for local/CI setup; experiment manifests require M3 implementation
- **Date:** 2026-11-09

**Subsequent consumer:** [ADR 0019](0019-offline-toolchain-replay.md) adds actual
locked-wheel capture and a fresh offline installed-test consumer. It leaves
bootstrap trust, durable retention and complete experiment manifests outside
that narrow toolchain slice.

## Context
Open dependency ranges and an unpinned interpreter/toolchain can change results at an unchanged source revision. The scaffold has no runtime dependencies and does not need a new environment service or storage system.

## Decision
Pin CPython 3.11.17 in `.python-version`. Configure CI for Ubuntu 24.04 and macOS 15 with the same `requirements-dev.lock` used locally. Generate the lock from `pyproject.toml`'s development extra and `requirements-toolchain.in`, including pip, setuptools, wheel, all transitive versions, environment markers, and distribution hashes. Install only hash-verified binary distributions, then install the local package without dependency resolution or isolated backend downloads. Validate the installed environment with `pip check`.

Use uv 0.13.5 as the recorded development-time lock generator, interpreter installer, and hash-verifying dependency installer; it is not a runtime dependency. GitHub's setup-python manifest provides Linux but no macOS build of 3.11.17, whereas uv's managed CPython builds cover both. Pin the setup-uv action to its reviewed commit and uv to 0.13.5, then create an unseeded managed environment and use `uv pip install --require-hashes --only-binary=:all: --reinstall` with the explicit environment interpreter and lock. The verified pip then builds/installs the local package. This preserves the same Python patch on both platforms without downgrading the security baseline. CI also builds and installs the wheel before running the tests, to exercise the distributed package. This is a documented rationale for development tooling, not authorization to add new runtime libraries. Intentional upgrades require lock review, a clean install, all quality checks, and platform CI evidence. No production service or storage is added.

The original seeded setup allowed pip, setuptools, wheel, and packaging to satisfy locked requirements without verifying their distribution bytes. A matching installed version is insufficient evidence of integrity. The unseeded setup removes that bootstrap, and `--reinstall` requires verification even if a matching distribution is already present. An offline acceptance check using the built repository wheel requires rejection of an invalid hash for an already installed package and successful reinstallation with the correct hash. uv itself, the setup action, the interpreter, and runner images remain explicit bootstrap trust inputs outside the Python dependency lock.

Experiment evidence must include the actual interpreter/OS/build, dependency/distribution provenance, lock checksum, numerical settings and source/artifact identifiers defined in `docs/environment.md`. Local exploration with a modified tree must preserve the patch and cannot become promotion evidence without clean-source replay. No complete experiment environment-manifest collector exists yet; ADR 0019
subsequently adds only bounded toolchain input/report capture and replay.

## Alternatives and limitations
Ranges alone cannot reproduce resolution. Freezing only package names/versions omits distribution integrity and interpreter/native settings. A container could pin more of the environment but adds maintenance that is not yet justified; retain manifests and verify each supported platform instead. OS runner images and external indexes may change or disappear, so exact offline replay needs retained verified distributions and the matching environment. Cross-platform floating-point identity is not assumed.
