# M2 reference-ledger scenario evidence

## Accepted gate and immutable source

As of 2026-11-10, only M2's **Reference ledger scenarios pass** gate is complete
on the evidence below. M1 remains active; every M1/M3 and remaining M2 gate is
open. This is acceptance of the bounded reference arithmetic, not the whole M2
milestone or an evaluable backtest.

- **Source:** [2362a9439e293e0e72051632e857a4737ed7c38d](https://github.com/matthiasdruhl/Quant-test/commit/2362a9439e293e0e72051632e857a4737ed7c38d).
- **Tree:** [1556dae6f3275dee5bb686fe9eef0c1721720bf1](https://api.github.com/repos/matthiasdruhl/Quant-test/git/trees/1556dae6f3275dee5bb686fe9eef0c1721720bf1).
- **Location:** pushed branch `codex/m2-reference-ledger`, unmerged. This record
  does not claim that `main` contains the ledger or the stacked changes below.
- **Implementation:** [reference_ledger.py at the tested revision](https://github.com/matthiasdruhl/Quant-test/blob/2362a9439e293e0e72051632e857a4737ed7c38d/src/quant_test/backtest/reference_ledger.py),
  with the [contract suite at that revision](https://github.com/matthiasdruhl/Quant-test/blob/2362a9439e293e0e72051632e857a4737ed7c38d/tests/contract/test_reference_ledger.py).

The [roadmap evidence rules](roadmap.md) require an immutable source, executable
CI results, acceptance results and independent review. They do not require this
gate to be merged first. This record pins the implementation revision above;
it does not assert its own revision or a future CI result.

## Financial approval and independent review

The repository owner/task user approved the five bounded financial decisions,
scope and scenarios at
[b216d63d3a63c39f8770f6f3500e7e75127da590](https://github.com/matthiasdruhl/Quant-test/commit/b216d63d3a63c39f8770f6f3500e7e75127da590)
in this Codex chat on 2026-11-10, replying **“Approve v1 as specified”** to the
exact-revision approval request. The
[original approval record](decisions/0017-explicit-reference-ledger.md#recorded-owner-approval)
and [reference specification](m2-reference-ledger-v1.md) retain that boundary.
This financial approval did not supply runtime acceptance, approve further
conventions, or authorize trading. No external identity verification is claimed.

The following review results were reported in the task conversation on
2026-11-10. Agent identifiers name separate review tasks; they are not public
transcript links, human GitHub approvals or invented external review records.

| Reviewer | Scope and outcome |
| --- | --- |
| `/root/independent_reviewer` | Final independent review found no blockers. All 178 focused tests passed. The reviewer independently executed the five literal scenarios and identity, zero-net obligation and valuation-cursor probes, and confirmed the five scenario sections were byte-identical to the approved baseline. |
| Parent `/root` | Read the complete 347-line core and 854-line suite. Independently executed all five references plus nine two-security prefixes, literal balance/equity reconciliation, independent obligation sums and rejection probes; all passed. Final document review corrected global cash reservation versus per-security sellability before the tested commit. |

The reviews checked cash/share transitions, global identity before time and
event-specific checks, old retries, rejected-ID reuse, permanent fill identity,
zero equity, zero-net obligations and valuation without cursor mutation. They
supply independent reference review for this bounded implementation, not source
or account authentication.

## Reference scenario acceptance

All expected money values below are integer hundredths of the explicitly declared
currency. Each linked function is pinned to the tested source revision; names and
line references identify the executable acceptance cases. Both regular and fresh
offline CI suites executed these cases on both platforms.

| Approved scenario | Exact executable case | Independent expected result and acceptance |
| --- | --- | --- |
| 1: buy fee and settlement | [`test_approved_scenario_1_buy_fee_recognition_and_full_settlement`](https://github.com/matthiasdruhl/Quant-test/blob/2362a9439e293e0e72051632e857a4737ed7c38d/tests/contract/test_reference_ledger.py#L125) | Opening cash 100000; buy 10 at 2000 plus fee 100 creates payable 20100, available cash 79900 and 10 held/unsettled shares. Equity is 99900 at mark 2000 or 101900 at 2200. Whole settlement leaves cash 79900, no payable and 10 sellable shares with unchanged equity. Passed. |
| 2: distinct partial fills and settlements | [`test_approved_scenario_2_distinct_partial_fills_costs_and_settlements`](https://github.com/matthiasdruhl/Quant-test/blob/2362a9439e293e0e72051632e857a4737ed7c38d/tests/contract/test_reference_ledger.py#L142) | Sell 4 at 2500 with fee 50, then 2 at 2400 with fee 25. Receivables total 14725; four held shares mark to 9600. Equity is 104225 before and after settlements; cash becomes 89850 then 94625 as the distinct obligations clear. Passed. |
| 3: reservations and unsettled shares | [`test_approved_scenario_3_reservation_and_unsettled_share_rejection`](https://github.com/matthiasdruhl/Quant-test/blob/2362a9439e293e0e72051632e857a4737ed7c38d/tests/contract/test_reference_ledger.py#L160) | From cash 10000, buy 6 at 1000 plus fee 100 reserves 6100. A further 4000 buy rejects; a 3000 buy leaves payable 9100, available 900 and nine unsettled shares. Equity is 9900. Settling the first buy makes six shares sellable; a seven-share sale rejects. Passed. |
| 4: identity and conflicts | [`test_approved_scenario_4_event_identity_and_settlement_conflicts`](https://github.com/matthiasdruhl/Quant-test/blob/2362a9439e293e0e72051632e857a4737ed7c38d/tests/contract/test_reference_ledger.py#L189) | Identical old fill/settlement retries leave state unchanged and equity 99900. Changed event facts, a new event reusing the fill ID, repeated settlement under a new ID and unknown settlement reject without changing retained state. Passed. |
| 5: equal-time order and valuation | [`test_approved_scenario_5_equal_time_order_and_invalid_valuation_requests`](https://github.com/matthiasdruhl/Quant-test/blob/2362a9439e293e0e72051632e857a4737ed7c38d/tests/contract/test_reference_ledger.py#L210) | With two unsettled shares, a sale before equal-time buy settlement rejects. Settlement then sale is valid: cash 8000, receivable 1200 and one held share. Equity at mark 1200 is 10400 throughout. Missing or different-instant marks reject. Passed. |

Additional executable cases cover cash reservations across securities and
per-security sellability, no financing from unsettled proceeds, immutable derived
outputs, complete mark sets, zero opening cash/marks/equity, exact units/currency,
standard integer/record/container boundaries and UTC offsets/folds/gaps/overflow.
Rejection preserves prior state and permits reuse of identities that were never
accepted. No simulator or provider dataset is substituted for these references.

## Local verification at the ledger revision

The parent reported these actual final-tree commands before committing the
ledger; they are local results, distinct from remote CI below.

| Command | Observed result |
| --- | --- |
| `.venv/bin/ruff check .` | Passed. |
| `.venv/bin/ruff format --check .` | 80 files already formatted. |
| `.venv/bin/mypy src` | No issues in 24 source files. |
| `.venv/bin/mypy scripts/verify_toolchain_replay.py` | No issues in one source file. |
| `.venv/bin/pytest` | 1498 passed, zero skipped. |

A wheel built from the clean committed ledger revision also passed the complete
fresh offline consumer locally: 17 installed distributions, 1498 tests passed,
zero skips and all five consumer return codes zero. The local record was
`/private/var/folders/b_/m0zgz30d6gb426x0txzzgtc00000gn/T/quant-ledger-parent-c3sfgp51/parent-acceptance.json`.
That temporary path is ephemeral local provenance, not a durable public artifact,
source authentication or a substitute for the remote results.

## Exact-head CI and offline replay

[CI run 42882681098, attempt 1](https://github.com/matthiasdruhl/Quant-test/actions/runs/42882681098/attempts/1)
checked out exact source `2362a9439e293e0e72051632e857a4737ed7c38d`.
Both [Ubuntu job 130062784641](https://github.com/matthiasdruhl/Quant-test/actions/runs/42882681098/job/130062784641)
and [macOS job 130062783967](https://github.com/matthiasdruhl/Quant-test/actions/runs/42882681098/job/130062783967)
succeeded. The CI observer fetched the actual logs, checked the source revision,
independently rehashed canonical input-manifest and success-report bytes and
checked every selected dependency wheel hash against the lock at that revision.

Both jobs reported Ruff success, 80 formatted files, mypy success for 24 source
files and the one verifier script, wheel build/install success and the old
preinstalled-wrong-hash negative acceptance check passing. Each regular suite
passed 1498 tests. Each full offline replay installed exactly 17 distributions
and passed 1498 tests with zero skips, failures or errors. All five consumer
return codes were zero on each platform.

Lock SHA-256:
`39c0c6c4defa0c2b5b8f0e4718088f5026ed286d2e9715d6c32b98c763b26441`.

| Observed input/report | Ubuntu | macOS |
| --- | --- | --- |
| Actual host | Linux x86_64, kernel `7.0.0-1017-azure`, CPython 3.11.17 | Darwin arm64, kernel `24.6.0`, CPython 3.11.17 |
| Canonical input manifest SHA-256 | `646532735ee601f5e4877227e72f0677fb7a56da4f04f7a8e18d13a3f9a11055` | `54f03f949a50cd863a9aaa3cb9562bf4da38c22ab6fd22c7caac5ee72b7401d3` |
| Canonical success report SHA-256 | `a56bb2cd7cdc1b2c9336cf090b58af7b682a2485302cf9c67b5ca5ddb41282a0` | `ef2c55d2fc3535541c28ff67c34c90b4c655095671cc1d2b00e3445f4ce5d5a1` |
| Built local package wheel SHA-256 | `fa8cb57a13f4fb232a93d8b0cb792f14a2c3e21c13f2f0fd245e5d21c3e0a942` | `edf024bc4bda5882c7a32044e25121e54c72c668b98079c4c8c80215c4dad872` |

The [offline verifier contract](decisions/0019-offline-toolchain-replay.md)
describes fresh unseeded installation, hash/inventory checks, installed import
origins, isolated tests and postchecks. These hashes/log observations do not pin
an OS image, guarantee CI retention or recover a complete experiment environment.
They prove neither market-data availability nor source/license rights.

## Remaining boundaries and gates

The ledger consumes explicit reference fills and marks. It supplies no actual
fills, market-data ingestion, fill simulator, settlement calendar, corporate
actions, FX, financing, fractional/short positions, taxes, cost-basis lots, realized
P&L, returns, target sizing, allocator, orders or broker path. Approval and test
success authorize none of those additions.

All M1 gates remain open, including provider rights/selection, source-availability
and identity evidence, coverage/completeness and evaluable dataset snapshots.
The owner reported no existing provider/dataset entitlement. Remaining M2 gates
require costs/partial fills/sessions/actions acceptance, future-data traps and
configuration/dataset-revision replay. Testing distinct explicit partial-fill
facts here does not implement partial-fill simulation or close that broader gate.
All M3 gates remain open, including allocation/sizing, complete strategy output,
statistical evaluation, holdout enforcement and full environment/derived lineage.
See the [roadmap](roadmap.md); M1 remains active.

## Appendix: reviewed pushed stack

These ten coherent parts were independently reviewed and pushed on separate
stacked branches, without merging, rebasing or creating new PRs for these parts.
The prior source-candidate base
[2684989b9f026091366f3e5f13f1240ff0883eb1](https://github.com/matthiasdruhl/Quant-test/commit/2684989b9f026091366f3e5f13f1240ff0883eb1)
is not one of these ten parts and is not represented here as new CI proof.
Each row links its immutable head and exact-head CI run; the observer verified
Ubuntu and macOS results for each. Counts are suite totals at each head, not
additional tests in that part. These records do not close other milestone gates.

| Branch | Immutable head | Tests | Exact-head CI | Scope and principal paths |
| --- | --- | --- | --- | --- |
| `codex/ci-branch-validation` | [d12d9cdb6bb348bcc79ffb1c86dedebbc66f69e2](https://github.com/matthiasdruhl/Quant-test/commit/d12d9cdb6bb348bcc79ffb1c86dedebbc66f69e2) | 393 | [42859269199](https://github.com/matthiasdruhl/Quant-test/actions/runs/42859269199) | `.github/workflows/ci.yml`: enable branch push quality checks; related CI documentation. |
| `codex/m1-receipt-linked-observations` | [b86d6a49279fea928f7ce8f7227d9cfa690773c1](https://github.com/matthiasdruhl/Quant-test/commit/b86d6a49279fea928f7ce8f7227d9cfa690773c1) | 535 | [42861249455](https://github.com/matthiasdruhl/Quant-test/actions/runs/42861249455) | `data/observation_records.py`, additive archive methods, fixtures/tests and [ADR 0012](decisions/0012-receipt-linked-observation-records.md). |
| `codex/m1-version-catalog-inventory` | [c34a75c0eb1ad3c0dc5d911a05bc2dcc30e17143](https://github.com/matthiasdruhl/Quant-test/commit/c34a75c0eb1ad3c0dc5d911a05bc2dcc30e17143) | 632 | [42863175703](https://github.com/matthiasdruhl/Quant-test/actions/runs/42863175703) | `data/catalog_inventories.py`, additive archive methods, fixtures/tests and [ADR 0013](decisions/0013-version-catalog-inventories.md). |
| `codex/m1-persisted-listing-histories` | [090b54fefc94987ec2bdbbf5baace34e9014b514](https://github.com/matthiasdruhl/Quant-test/commit/090b54fefc94987ec2bdbbf5baace34e9014b514) | 741 | [42865747498](https://github.com/matthiasdruhl/Quant-test/actions/runs/42865747498) | `data/listing_records.py`, additive archive methods, literal chain/tests and [ADR 0014](decisions/0014-persisted-listing-history-records.md). |
| `codex/m1-persisted-membership-histories` | [c48c605fbc9ccb582c42244776ea0b43335264e4](https://github.com/matthiasdruhl/Quant-test/commit/c48c605fbc9ccb582c42244776ea0b43335264e4) | 844 | [42867939994](https://github.com/matthiasdruhl/Quant-test/actions/runs/42867939994) | `data/membership_records.py`, additive archive methods, cross-module fixtures/tests and [ADR 0015](decisions/0015-persisted-membership-history-records.md). |
| `codex/m1-universe-listing-replay` | [53b0d7f98a0d9682de3c9d3d5675b51cc8cb5bb1](https://github.com/matthiasdruhl/Quant-test/commit/53b0d7f98a0d9682de3c9d3d5675b51cc8cb5bb1) | 1018 | [42870823940](https://github.com/matthiasdruhl/Quant-test/actions/runs/42870823940) | `data/universe_listing_replays.py`, additive archive methods, report fixture/tests and [ADR 0016](decisions/0016-historical-universe-listing-replay.md). |
| `codex/m2-ledger-reference-proposal` | [b216d63d3a63c39f8770f6f3500e7e75127da590](https://github.com/matthiasdruhl/Quant-test/commit/b216d63d3a63c39f8770f6f3500e7e75127da590) | 1018 | [42872171530](https://github.com/matthiasdruhl/Quant-test/actions/runs/42872171530) | Documentation-only [ADR 0017](decisions/0017-explicit-reference-ledger.md) and [five-scenario specification](m2-reference-ledger-v1.md), with discoverability links; later exact-revision approval is recorded above. |
| `codex/m3-target-batch-lifecycle` | [2876367dea4193dcd425f4e4cb39273e00b66384](https://github.com/matthiasdruhl/Quant-test/commit/2876367dea4193dcd425f4e4cb39273e00b66384) | 1193 | [42874345117](https://github.com/matthiasdruhl/Quant-test/actions/runs/42874345117) | `strategies/targets.py`, contract tests and [ADR 0018](decisions/0018-immutable-target-batch-lifecycle.md); quantity/lifecycle subset only. |
| `codex/offline-toolchain-replay` | [80e25dac10bfddcb5d6a79c0fe5250a422d628df](https://github.com/matthiasdruhl/Quant-test/commit/80e25dac10bfddcb5d6a79c0fe5250a422d628df) | 1320 | [42879337513](https://github.com/matthiasdruhl/Quant-test/actions/runs/42879337513) | `scripts/verify_toolchain_replay.py`, focused tests, CI append and [ADR 0019](decisions/0019-offline-toolchain-replay.md); actual offline toolchain consumer. |
| `codex/m2-reference-ledger` | [2362a9439e293e0e72051632e857a4737ed7c38d](https://github.com/matthiasdruhl/Quant-test/commit/2362a9439e293e0e72051632e857a4737ed7c38d) | 1498 | [42882681098](https://github.com/matthiasdruhl/Quant-test/actions/runs/42882681098) | `backtest/reference_ledger.py`, 178 focused contract tests, approval/API record and related documentation; detailed acceptance above. |

Module paths in the table are relative to `src/quant_test/` unless prefixed by
`scripts/`, `.github/` or `docs/`. Every part includes its directly related
documentation updates; immutable commit diffs give the complete changed paths.

For the first CI-trigger part, final evidence includes
[attempt 2 of run 42859269199](https://github.com/matthiasdruhl/Quant-test/actions/runs/42859269199/attempts/2):
the original queued macOS job was cancelled, and its failed-job
retry passed. This is not a claim that the initial attempt was entirely green.
For the offline-toolchain part, a real pre-push consumer at `bfc874a` rejected
incompatible uv flags before installation. The follow-up at the pushed `80e25da`
fixed that command and passed actual replay; the failed pre-push attempt is not
represented as a successful acceptance result.
