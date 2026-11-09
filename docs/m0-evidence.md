# M0 verification and owner sign-off

## Status
[PR #1](https://github.com/matthiasdruhl/Quant-test/pull/1) was merged into `main` at [a250a81790fc95993378c5c231f32575fb1aa065](https://github.com/matthiasdruhl/Quant-test/commit/a250a81790fc95993378c5c231f32575fb1aa065) on 2026-11-09. Owner Matthias Druhl explicitly accepted the M0 technical baseline on 2026-11-09 in the task conversation. The active repository ruleset is recorded below. M0 remains current: the subsequent hash-verification correction still requires CI on its exact revision and independent review. Owner acceptance of the earlier baseline does not establish verification of this correction.

## Immutable technical evidence
- Initial implementation revision: [5d9ce72c92fd0bf532146692adfc68aeb730aef1](https://github.com/matthiasdruhl/Quant-test/commit/5d9ce72c92fd0bf532146692adfc68aeb730aef1). Final PR head: [f458089564972cbbab12664c8fefa7b534419789](https://github.com/matthiasdruhl/Quant-test/commit/f458089564972cbbab12664c8fefa7b534419789), with passing [current-head CI run 42681692878](https://github.com/matthiasdruhl/Quant-test/actions/runs/42681692878).
- GitHub [CI run 42681341065](https://github.com/matthiasdruhl/Quant-test/actions/runs/42681341065) completed successfully for the initial implementation revision `5d9ce72` on 2026-11-09. The final PR head has its separate CI run linked above.
- [Ubuntu 24.04 job](https://github.com/matthiasdruhl/Quant-test/actions/runs/42681341065/job/129376372700) and [macOS 15 job](https://github.com/matthiasdruhl/Quant-test/actions/runs/42681341065/job/129376372174) both passed every step.

The historical job logs establish the following on both platforms. These runs used the original seeded environment and do **not** prove distribution hash verification for every locked package:

| Acceptance item | Executed command / observed result |
| --- | --- |
| Exact interpreter and dependency install command | Managed CPython 3.11.17; `pip install --require-hashes --only-binary=:all: -r requirements-dev.lock` succeeded, but preinstalled seed packages bypassed hash verification |
| Compatible installed dependencies | `python -m pip check`: No broken requirements found |
| Lint | `ruff check .`: All checks passed |
| Format | `ruff format --check .`: 30 files already formatted |
| Types | `mypy src`: Success, no issues in 10 source files |
| Installable distribution | Wheel built with `--no-deps --no-build-isolation`, installed, and data/time module imports succeeded |
| Timestamp reference and negative cases | `pytest -q`: 33 passed against the installed distribution |

Local validation also passed all four quality checks on CPython 3.11.17. Direct wheel inspection/import verified all ten source modules. Ignore-boundary checks verified that new `src/quant_test/data/` source is visible while repository-root data/artifact/output paths remain ignored. Local documentation links resolved; these checks are supplementary to the remote results.

## Hash-verification correction: pending remote verification
Independent audit found that the original `uv venv --seed` installed pip, setuptools, wheel, and packaging before the hash-locked install. pip reported matching versions as already satisfied, so the historical CI results cannot substantiate the original claim that all third-party distribution bytes were verified.

The correction creates an unseeded environment and runs uv 0.13.5 with `--require-hashes --only-binary=:all: --reinstall` against the explicit environment interpreter. No lock versions, hashes, runtime contracts, or quality gates change. [ADR 0003](decisions/0003-reproducible-environments.md) records the rationale and bootstrap trust boundary. The [offline acceptance procedure](environment.md#offline-hash-verification-acceptance-check) uses the actual built repository wheel to reject an invalid hash even when the matching package is already installed, then accepts the correct hash. Its local result is supplementary evidence; an immutable correction revision, successful Ubuntu/macOS CI, and independent review must be attached before closing this gap.

Local correction validation on 2026-11-09 used CPython 3.11.17 and uv 0.13.5: `ruff check .` passed; `ruff format --check .` reported 35 files already formatted; `mypy src` reported no issues in 11 source files; `pytest` passed 61 tests; `pip check` found no broken requirements. The repository wheel built with `--no-deps --no-build-isolation --no-index`, and `scripts/verify_hash_install.py` passed the empty-environment, preinstalled invalid-hash rejection, and valid-hash reinstall checks. A complete fresh third-party lock installation was not run locally because no retained wheelhouse was available; the correction's two-platform CI remains required.

## Review scope and remaining acceptance
The original M0 patch preserves historical source replay and introduces explicit actual-platform eligibility; it widens unknown event time handling, rejects invalid required times, and fixes DST ordering with UTC comparisons. ADR 0002 records the public API changes. ADR 0003 records pinned development tooling, dependency hashes, the cross-platform interpreter installer, and environment evidence. ADR 0004 and the strategy/research contracts specify future target and holdout behavior with reference cases; their runtime implementations are not part of M0. No runtime dependency, trading adapter, deployment, or account connection is added.

The owner accepted the M0 technical baseline on 2026-11-09, including its source/contracts and technical evidence. GitHub's required approval count is zero; that setting does not constitute an independent technical review. Do not infer review approval from a merge or the owner's connected identity. Independent review and CI for the hash-verification correction remain pending. Keep M0 checklist boxes open until that evidence is recorded.

## Repository protections: active ruleset
The parent task independently verified active [ruleset 26885025](https://api.github.com/repos/matthiasdruhl/Quant-test/rulesets/26885025) for `main` on 2026-11-09. It requires a pull request, successful `quality (ubuntu-24.04)` and `quality (macos-15)` checks with the branch up to date, and resolved review conversations. It prohibits force pushes and deletion. Its required GitHub approval count is zero, and its bypass actor list is empty. This supersedes the earlier observation that protection was unavailable; no plan, billing, visibility, or ruleset settings are changed by this correction.

## Closing M0
Attach the correction's immutable source revision, passing CI on both configured platforms, and independent review to this record before marking M0 complete. Preserve the historical CI limitation above. M1 implementation remains separately scoped and does not imply M0 acceptance.
