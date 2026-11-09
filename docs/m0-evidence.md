# M0 verification and owner sign-off

## Status
[PR #1](https://github.com/matthiasdruhl/Quant-test/pull/1) was merged into `main` at [a250a81790fc95993378c5c231f32575fb1aa065](https://github.com/matthiasdruhl/Quant-test/commit/a250a81790fc95993378c5c231f32575fb1aa065) on 2026-11-09. Owner Matthias Druhl replied "Accept the M0 baseline" in the task conversation on 2026-11-09. The subsequent hash-verification correction merged in [PR #4](https://github.com/matthiasdruhl/Quant-test/pull/4), with successful CI on GitHub's PR synthetic merge and then on the exact merged `main` revision. Independent review records and the active repository ruleset are recorded below. Owner acceptance applies to the earlier baseline; verification of the correction rests on its separate CI and review evidence.

All five M0 gates have evidence for completion. The protection gate records an owner-approved active ruleset; the available evidence does not identify its configuring actor.

## Immutable technical evidence
- Initial implementation revision: [5d9ce72c92fd0bf532146692adfc68aeb730aef1](https://github.com/matthiasdruhl/Quant-test/commit/5d9ce72c92fd0bf532146692adfc68aeb730aef1). Final PR head: [f458089564972cbbab12664c8fefa7b534419789](https://github.com/matthiasdruhl/Quant-test/commit/f458089564972cbbab12664c8fefa7b534419789), associated with passing [PR CI run 42681692878](https://github.com/matthiasdruhl/Quant-test/actions/runs/42681692878). An associated PR head is not necessarily the checked-out test revision.
- GitHub [CI run 42681341065](https://github.com/matthiasdruhl/Quant-test/actions/runs/42681341065), associated with initial implementation revision `5d9ce72`, completed successfully on 2026-11-09. The final PR head has its separate associated CI run linked above.
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

## Hash-verification correction: verified revision and CI
Independent audit found that the original `uv venv --seed` installed pip, setuptools, wheel, and packaging before the hash-locked install. pip reported matching versions as already satisfied, so the historical CI results cannot substantiate the original claim that all third-party distribution bytes were verified.

The correction creates an unseeded environment and runs uv 0.13.5 with `--require-hashes --only-binary=:all: --reinstall` against the explicit environment interpreter. No lock versions, hashes, runtime contracts, or quality gates change. [ADR 0003](decisions/0003-reproducible-environments.md) records the rationale and bootstrap trust boundary. The [offline acceptance procedure](environment.md#offline-hash-verification-acceptance-check) uses the actual built repository wheel to reject an invalid hash even when the matching package is already installed, then accepts the correct hash.

- Correction head: [5c7b43696d49eeb958425d19d7d5d296ea62837e](https://github.com/matthiasdruhl/Quant-test/commit/5c7b43696d49eeb958425d19d7d5d296ea62837e), merged through [PR #4](https://github.com/matthiasdruhl/Quant-test/pull/4) at [6e6ce45d88a90524152da8c12a7c198ae7df224b](https://github.com/matthiasdruhl/Quant-test/commit/6e6ce45d88a90524152da8c12a7c198ae7df224b) on 2026-11-09.
- PR [CI run 42694437775](https://github.com/matthiasdruhl/Quant-test/actions/runs/42694437775) was associated with head `5c7b43696d49eeb958425d19d7d5d296ea62837e`, but its checkout logs show GitHub's synthetic merge [6cc20b3dc24e3dc43d107f90110d033879ea1cc4](https://github.com/matthiasdruhl/Quant-test/commit/6cc20b3dc24e3dc43d107f90110d033879ea1cc4) into base `7b5bebc`. Both [Ubuntu 24.04 job 129422377110](https://github.com/matthiasdruhl/Quant-test/actions/runs/42694437775/job/129422377110) and [macOS 15 job 129422376531](https://github.com/matthiasdruhl/Quant-test/actions/runs/42694437775/job/129422376531) succeeded. This is PR integration evidence, not a literal-head checkout.
- Post-merge push [CI run 42694728391](https://github.com/matthiasdruhl/Quant-test/actions/runs/42694728391) checked out exact merged-`main` revision `6e6ce45d88a90524152da8c12a7c198ae7df224b`: successful [Ubuntu job 129423394746](https://github.com/matthiasdruhl/Quant-test/actions/runs/42694728391/job/129423394746) and [macOS job 129423394287](https://github.com/matthiasdruhl/Quant-test/actions/runs/42694728391/job/129423394287). This supplies CI evidence for the immutable merged source used to close the gates below.

The correction head and merged-`main` revision have identical source tree `b0b9e60782c27d9197cab69303acacd0476f0201`. This connects the reviewed correction to the source tested in the post-merge run without conflating the PR head with GitHub's synthetic merge.

The PR synthetic-merge and exact merged-`main` logs establish these acceptance results on both platforms:

| Acceptance item | Executed command / observed result |
| --- | --- |
| Complete applicable lock installation | Unseeded managed CPython 3.11.17 environment; uv 0.13.5 installed 16 applicable packages with `uv pip install --python .venv/bin/python --require-hashes --only-binary=:all: --reinstall -r requirements-dev.lock` |
| Compatible installed dependencies | `python -m pip check`: no broken requirements |
| Lint and formatting | `ruff check .` and `ruff format --check .`: passed |
| Types | `mypy src`: passed |
| Installable distribution | Wheel built with `--no-deps --no-build-isolation`, installed, and data/time module imports succeeded |
| Negative hash fixture | `python scripts/verify_hash_install.py dist/*.whl`: empty environment verified, preinstalled package rejected an invalid hash, valid reinstall succeeded |
| Timestamp and revision fixtures | `pytest -q`: 61 passed against the installed distribution |

Local correction validation on 2026-11-09 used CPython 3.11.17 and uv 0.13.5: `ruff check .` passed; `ruff format --check .` reported 35 files already formatted; `mypy src` reported no issues in 11 source files; `pytest` passed 61 tests; `pip check` found no broken requirements. The repository wheel built with `--no-deps --no-build-isolation --no-index`, and `scripts/verify_hash_install.py` passed the empty-environment, preinstalled invalid-hash rejection, and valid-hash reinstall checks. A complete fresh third-party lock installation was not run locally because no retained wheelhouse was available; the remote runs above supply that evidence.

## Independent review record
The original M0 patch preserves historical source replay and introduces explicit actual-platform eligibility; it widens unknown event time handling, rejects invalid required times, and fixes DST ordering with UTC comparisons. ADR 0002 records the public API changes. ADR 0003 records pinned development tooling, dependency hashes, the cross-platform interpreter installer, and environment evidence. ADR 0004 and the strategy/research contracts specify future target and holdout behavior with reference cases; their runtime implementations are not part of M0. No runtime dependency, trading adapter, deployment, or account connection is added.

The following independent agent reviews were reported in the task conversation on 2026-11-09. This section is their evidence record; the task identifiers identify separate reviewers, but are not public transcript links or GitHub approving reviews. The correction reviews concern head `5c7b43696d49eeb958425d19d7d5d296ea62837e` linked above.

| Reviewer task | Scope and observed outcome |
| --- | --- |
| `/root/m0_independent_review` | Read-only M0 baseline audit found no timestamp-contract defect. It discovered the seeded-install hash-verification gap documented above; the original CI therefore did not close the hash-verification acceptance item. |
| `/root/m0_ci_security_review` | Independent correction/installer audit found no blocker. Its experiment removed `--reinstall` and caused the bad-hash acceptance check to fail, demonstrating that the negative check detects this regression. |
| `/root/m0_ci_docs_review` | Independent evidence/governance audit found no blocker; minor clarity fixes were addressed in the correction. |

The owner's baseline acceptance, the independent review findings, and the correction's CI are separate evidence. GitHub's required approval count is zero; that setting and the merges do not constitute independent technical review or owner acceptance of the correction.

## Repository protections: active ruleset
The parent task independently verified active [ruleset 26885025](https://api.github.com/repos/matthiasdruhl/Quant-test/rulesets/26885025) for `main` on 2026-11-09. It requires a pull request, successful `quality (ubuntu-24.04)` and `quality (macos-15)` checks with the branch up to date, and resolved review conversations. It prohibits force pushes and deletion. Its required GitHub approval count is zero, and its bypass actor list is empty. This supersedes the earlier observation that protection was unavailable; no plan, billing, visibility, or ruleset settings are changed by this correction.

Owner: Matthias Druhl. Verification and acceptance date: 2026-11-09. Verifiable outcome: the ruleset is active with the settings above. In the task conversation, the owner delegated the protection choice and then instructed, "If it looks good approve it." The parent task assessed the verified settings as suitable for the current solo-owner repository and accepted the active policy under that authority. The roadmap gate therefore records an owner-approved active ruleset. The API evidence does not identify who configured it, and this record does not attribute that action to the owner. Zero required GitHub approvals remains an explicit policy limitation; independent agent review is recorded separately above.

## M0 gate evidence

| Roadmap gate | Evidence and outcome as of 2026-11-09 |
| --- | --- |
| Versioned architecture, source boundaries, temporal and trading contracts accepted in review | Complete: [baseline final head f458089](https://github.com/matthiasdruhl/Quant-test/commit/f458089564972cbbab12664c8fefa7b534419789), owner's dated acceptance and independent M0 audit above; [post-merge CI 42694728391](https://github.com/matthiasdruhl/Quant-test/actions/runs/42694728391) verifies the resulting merged source at `6e6ce45d88a90524152da8c12a7c198ae7df224b`. Historical baseline PR CI is supplementary evidence as described above. |
| Minimal installable package and hash-locked CI verified | Complete: merged revision `6e6ce45d88a90524152da8c12a7c198ae7df224b`, [post-merge CI 42694728391](https://github.com/matthiasdruhl/Quant-test/actions/runs/42694728391) with wheel installation and negative hash fixture on both platforms, and independent correction/installer review of the identical correction source tree, all linked or recorded above. |
| Time-availability primitive and explicit unimplemented modules verified in CI/review | Complete: baseline revision/review above and [post-merge CI 42694728391](https://github.com/matthiasdruhl/Quant-test/actions/runs/42694728391)'s 61 passing tests on both platforms. The [merged source tree](https://github.com/matthiasdruhl/Quant-test/tree/6e6ce45d88a90524152da8c12a7c198ae7df224b/src/quant_test) preserves the timestamp primitive and explicit module boundaries; no future trading or research implementation is implied. |
| CI actually run successfully on GitHub | Complete: [post-merge CI 42694728391](https://github.com/matthiasdruhl/Quant-test/actions/runs/42694728391) checked out exact merged revision `6e6ce45d88a90524152da8c12a7c198ae7df224b`; both platform jobs are linked above, and independent evidence/governance review is recorded above. PR CI 42694437775 separately passed on GitHub's synthetic merge. |
| Owner-approved active repository protections | Complete: active ruleset 26885025, owner Matthias Druhl's delegated acceptance instruction, parent task assessment, and verification/acceptance date 2026-11-09 are recorded above. This establishes approval of the active policy, not the configuring actor. |

The hash-verification gap is closed by the correction evidence; the historical seeded-install limitation remains part of the audit record. All M0 gates are complete on this evidence. M1 implementation and acceptance remain separately scoped.
