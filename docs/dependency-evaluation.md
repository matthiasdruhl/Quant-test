# Dependency evaluation and reuse-first delivery plan

**Status:** Proposed evaluation backlog, not an adopted stack. Updated 2026-11-13.
**Authority:** [ADR 0012](decisions/0012-open-source-first-dependency-strategy.md), [architecture](architecture.md), [roadmap](roadmap.md), [invariants](invariants.md), [data contracts](data-contracts.md), [research protocol](research-protocol.md).
**Goal:** Reach one reproducible, independently checked, end-to-end U.S. equities swing-research run with minimal custom infrastructure. No live execution.

## Decision matrix

"Own" means maintain project-specific policy/contracts, **not** reimplement a mature math or storage library. Nothing listed as "evaluate" is currently installed or selected in the platform.

| Capability | Direction | Candidates / existing code | Decision criteria / boundary |
| --- | --- | --- | --- |
| Point-in-time availability, revised source records, provenance | **Keep/own critical semantics** | Existing `core.time`, `data.versions`, `data.admission`, `data.listings`, `data.universes` | Independent future-data, correction, delisting, universe-membership and negative tests must remain true after integration |
| Raw payload archive, receipt codec and quality inventories | **Preserve now; evaluate simplifying** | Existing `data.raw_archive`, `data.receipts`, `data.receipt_sets`; external object/dataset/versioning tools | Compare integrity, source claims, reproducibility, crash behavior, replay and operational cost; no deletion before parity and migration plan |
| Curated analytical storage | **Reuse** | DuckDB, Parquet | Stable schema, deterministic snapshots, version provenance and fixture-based replay; not a replacement for missing evidence of information availability |
| Provider ingestion and finance/fundamental queries | **Wrap/reuse** | OpenBB or direct licensed/official provider APIs | Real-world historical coverage, data rights, costs, revision/availability evidence, rate limits, identity, corrections and reliability |
| Backtesting/simulation and accounting | **Reuse after bake-off** | Qlib (first research candidate), LEAN (event-driven comparison) | Compare identical history and baseline; session/order/fill/cost/corporate-action/ledger semantics, speed, host compatibility, licensing and API complexity |
| Technical indicators, statistics, ML | **Reuse** | NumPy/pandas/scikit-learn/LightGBM/PyTorch and appropriate existing statistics packages | Versioned experiments, no future-trained artifacts, consistent training partitions |
| Experiment registry and performance analytics | **Reuse or adapt** | Qlib built-ins, MLflow, QuantStats as needed | Avoid two overlapping registries; immutable run IDs, failure logging, environment and source snapshot pins, research/holdout safeguards |
| Strategy representation and portfolio targets | **Own a small domain adapter** | Existing `strategy-contract.md`; chosen engine adapters | Keep units, expiry, snapshot identity, target-to-order separation, allocation and independent risk checks |
| AI-assisted research workflows | **Evaluate later** | RD-Agent, bounded Codex/Claude agents | Only after deterministic baseline; limited tools, hypothesis registration, fixed budgets and zero order/deploy credentials |
| Macro, SEC and disclosures | **Reuse source APIs; own temporal feature rules** | FRED, SEC EDGAR, official public filings, provider adapters | Source availability, amendments, release timing, uncertainty; no retroactively available features |
| Paper brokerage and live execution | **Defer** | Official broker APIs/SDKs if authorized | Independent risk veto, idempotency, reconciliation, stop switch, credentials separation and failure drills |
| Dashboard/UI | **Defer or reuse** | Simple notebooks, existing research tools, Streamlit | Do not build custom UI before a validated experiment workflow exists |
| Alternative data (e.g. satellite) | **Defer** | Licensed data/vendor sources | Show incremental value above baseline, operational feasibility, permissions and cost |

## Evaluation scoring rubric

Score each shortlisted candidate 0–5 and capture **evidence links**, versions, environment, test output, and key unknowns. Weights guide discussion, **not** an automatic approval:

| Criterion | Weight |
| --- | ---: |
| Historical correctness and testability (availability, survivorship, ledger semantics) | 30% |
| Integration with existing contracts and reproducible runs | 20% |
| Maintenance, security, and license/dependency obligations | 15% |
| Coverage of our real strategy/research needs | 15% |
| Operational cost, data rights, and ease of local setup | 10% |
| Performance and scale for measured workloads | 10% |

**Hard stops, regardless of score:** unknown/unacceptable license rights, inability to preserve decision-time eligibility, irreproducible results, unfixable reference ledger mismatches, unavoidable unsafe live authorization, or unsupported runtimes without an acceptable isolation strategy. Resolve data licensing separately from software licensing.

Record each trial as: name/version/commit, license checked on date, setup commands and environment, dataset/source permission, evidence URLs, reference cases passed/failed, resource cost, integration effort, risks, and `adopt | wrap | build | defer | reject` conclusion. No invented benchmarks.

## First vertical slice: deterministic research, no agent

### Prerequisites

1. Pick a small **lawfully usable** price/volume dataset with split/dividend information as relevant and explicit coverage/adjustment rules. Use synthetic **test fixtures** only for correctness tests, not as actual market-performance evidence.
2. Define a fixed equity universe (including at least one delisted-security test case when real data permits), historical date range, trading calendar, initial capital, commission/slippage rules, fill timing, and explicit raw/adjusted price convention.
3. Freeze source snapshot(s) and provenance or document data gaps that preclude a claim of point-in-time correctness.
4. Pin baseline `main`, evaluated framework release/version, Python/container/toolchain versions, seeds, strategy configuration and reference fixture expectations.

### Trial A — Qlib

- Run a simple, transparent daily-frequency momentum or mean-reversion baseline in an isolated evaluation environment, without modifying production runtime dependencies.
- Connect one reproducible dataset through the minimum adapter. Document any data conversions and information lost at the boundary.
- Export run manifest, orders/fills, ledger, transactions, equity/returns, commissions, benchmark and evaluation metrics.
- Run our temporal and accounting challenge cases against its real scheduling and feed semantics. If an invariant cannot be enforced, document the blocker and required adapter.

### Trial B — LEAN

- Use **the same dataset, strategy definition, exposure rules, fill/cost assumptions, and date range** where possible.
- Reconcile order timing, cash, fills, corporate actions, and final equity against the reference ledger and Trial A; explain any legitimate engine convention differences.
- Measure setup burden, local dependencies/Docker needs, iteration time, and integration effort. Do not treat discordant returns as an unexplained acceptable result.

### Decision gate

Select **one primary** simulator only after independent review of hard stops, reconciliation, compatibility, cost, and maintenance. If neither passes, evaluate a third candidate or justify the minimum narrowly scoped custom engine behavior with a separate ADR. Do not combine two complete engines by default.

### Minimum acceptance evidence

- The same fixed baseline and dataset can be rerun from a recorded environment and reproduce outputs within documented numeric tolerances.
- Independent expected ledgers match for buy/sell, fees, partial or zero fills (if supported), splits/dividends, missing observations, sessions and cash conservation.
- A decision at time `T` cannot consume later observations, revisions, future-trained features or same-bar close fills unless timing genuinely makes them available.
- Historical listing/delisting and universe selection do not silently switch to current constituents.
- Successful **and failed** runs are registered with snapshot/version/config hashes and negative-case results.
- The chosen external software and data rights are checked; target Python 3.11.17 and Mac/Linux environments are either supported by evidence or isolated by an explicitly approved runtime.
- Independent review provides a clear pass/fail disposition. No simulated return is labeled a proven edge.

## Next work in order

1. **Inventory and mapping:** map each implemented data primitive and unresolved M1 gate to candidate external components; mark keep/wrap/replace/defer, without deleting code.
2. **License/data feasibility:** record provider permission, subscriptions, software license/notice obligations and baseline environment compatibility. Check Qlib dependencies (including its MLflow constraints), LEAN local-runtime requirements, and the *actual* installed package versions rather than GitHub `main` assumptions.
3. **Two bounded spikes:** Qlib and LEAN; run the same reference examples and make discrepancies reproducible.
4. **Primary-engine ADR:** approve one integration approach, explicit non-goals, migration plan, and cost/maintenance trade-offs.
5. **Complete minimal end-to-end research run:** data → eligible observations → baseline → simulation → independent analysis → saved run.
6. **Then** evaluate RD-Agent / MLflow / OpenBB expansion only where the chosen engine and actual research workflow leave a proven gap.

## What remains unchanged

M0 evidence stands. M1 acceptance is still open. Existing temporal and receipt tests are not evidence that provider ingestion or full historical datasets exist. No paper/live trading, broker authorization, autonomous deployment, or profitability claim is approved. The original [roadmap](roadmap.md) remains the source of milestone gates; this file specifies how candidate adoption should be assessed.

## Candidate source links (verify actual versions and terms before use)

- [Qlib](https://github.com/microsoft/qlib) (research and ML platform)
- [QuantConnect LEAN](https://github.com/QuantConnect/Lean) (event-driven simulation)
- [Microsoft RD-Agent](https://github.com/microsoft/RD-Agent) (agent research candidate)
- [OpenBB](https://github.com/openbq-org/OpenBB) (provider integrations; providers may have separate terms)
- [DuckDB](https://duckdb.org/), [Apache Parquet](https://parquet.apache.org/), [MLflow](https://github.com/mlflow/mlflow)
- [VectorBT terms](https://vectorbt.dev/terms/) (commercial-usage caution)
- [SEC developer resources](https://www.sec.gov/about/developer-resources), [FRED API](https://fred.stlouisfed.org/docs/api/fred/)
