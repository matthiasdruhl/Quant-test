# M0 verification and owner sign-off

## Status
The implementation and automated verification are ready for owner review in [PR #1](https://github.com/matthiasdruhl/Quant-test/pull/1). M0 remains current until owner/reviewer acceptance and the repository-protection disposition are recorded. An implementation review by the same coding agent is not independent owner approval, and the PR has not been merged.

## Immutable technical evidence
- Reviewed implementation revision: [5d9ce72c92fd0bf532146692adfc68aeb730aef1](https://github.com/matthiasdruhl/Quant-test/commit/5d9ce72c92fd0bf532146692adfc68aeb730aef1).
- GitHub [CI run 42681341065](https://github.com/matthiasdruhl/Quant-test/actions/runs/42681341065) completed successfully for that revision on 2026-11-09. This evidence describes the linked revision; any later PR head must pass its own checks before merge. The PR records current-head CI evidence.
- [Ubuntu 24.04 job](https://github.com/matthiasdruhl/Quant-test/actions/runs/42681341065/job/129376372700) and [macOS 15 job](https://github.com/matthiasdruhl/Quant-test/actions/runs/42681341065/job/129376372174) both passed every step.

The job logs establish the following on both platforms:

| Acceptance item | Executed command / observed result |
| --- | --- |
| Exact interpreter and hash-locked dependencies | Managed CPython 3.11.17; `pip install --require-hashes --only-binary=:all: -r requirements-dev.lock` succeeded |
| Compatible installed dependencies | `python -m pip check`: No broken requirements found |
| Lint | `ruff check .`: All checks passed |
| Format | `ruff format --check .`: 30 files already formatted |
| Types | `mypy src`: Success, no issues in 10 source files |
| Installable distribution | Wheel built with `--no-deps --no-build-isolation`, installed, and data/time module imports succeeded |
| Timestamp reference and negative cases | `pytest -q`: 33 passed against the installed distribution |

Local validation also passed all four quality checks on CPython 3.11.17. Direct wheel inspection/import verified all ten source modules. Ignore-boundary checks verified that new `src/quant_test/data/` source is visible while repository-root data/artifact/output paths remain ignored. Local documentation links resolved; these checks are supplementary to the remote results.

## Review scope and remaining acceptance
The patch preserves historical source replay and introduces explicit actual-platform eligibility; it widens unknown event time handling, rejects invalid required times, and fixes DST ordering with UTC comparisons. ADR 0002 records the public API changes. ADR 0003 records pinned development tooling, dependency hashes, the cross-platform interpreter installer, and environment evidence. ADR 0004 and the strategy/research contracts specify future target and holdout behavior with reference cases; their runtime implementations are not part of M0. No runtime dependency, trading adapter, deployment, or account connection is added.

Owner/reviewer acceptance is still needed for the source/contracts, ADRs 0002–0004, dependency/tooling selection, and the linked test evidence. GitHub created this PR under the owner's connected identity; an approval must not be fabricated from that same identity. Use an independent collaborator's review, or record explicit owner sign-off separately when working alone. Keep M0 checklist boxes open until the applicable review evidence is recorded.

## Repository protections: observed limitation and proposed policy
On 2026-11-09, GitHub's `branches/main` API reported `protected: false`. The repository is private. The rulesets API returned HTTP 403 with: "Upgrade to GitHub Pro or make this repository public to enable this feature." The protection-detail endpoint separately returned "Resource not accessible by integration." These are service/account constraints, not failing code checks. No plan, billing, visibility, protection, or bypass setting has been changed.

For an eligible private-repository plan, the proposed owner-configured rules for `main` are:
- Require a pull request and successful `quality (ubuntu-24.04)` and `quality (macos-15)` checks on the current head; require the branch to be up to date.
- Require review conversations to be resolved; prohibit force pushes and branch deletion.
- Require one independent approval when a separate collaborator is available. GitHub does not permit authors to approve their own PR; a solo-owner workflow must explicitly record owner sign-off rather than inventing a second reviewer.
- Give automated actors no protection bypass or merge/deployment authority. Record any owner emergency override and rerun verification.

The owner must decide whether to enable an eligible private-repository plan and configure the rules, or explicitly accept and record the current unavailability under M0's "where available" clause. A temporary manual workflow would require feature branches, green current-head CI, explicit owner review, and owner-performed merges; it cannot prevent direct pushes or bypasses and must never be described as enforced protection. This document proposes that workflow but does not approve an exception. The repository remains private.

## Closing M0
Record the review/sign-off and protection decision in the PR with the reviewed head revision. Merge only after current-head checks pass and the owner authorizes the merge. Then attach the evidence to the roadmap gates and mark M0 complete. Subsequent M1 implementation must remain a separately scoped task.
