# ADR 0012: Open-source-first dependency and build-versus-reuse policy

- **Date:** 2026-11-13
- **Status:** Accepted as a planning policy; individual dependencies are **not approved or adopted**
- **Scope:** Research, data, simulation, AI assistance, analytics, portfolio, and future execution
- **Supersedes:** No existing data, time, risk, or acceptance invariant
- **Implementation:** Documentation-only decision; no new runtime dependencies or trading permissions

## Context

Quant-test is a research-first U.S. equities platform. M0 is complete and M1 is partly implemented, but the repository has no trading strategy, backtest engine, brokerage integration, or live execution. The existing roadmap reserved many subsystems for custom implementation before evaluating mature open-source solutions.

Building simulation, accounting, research workflow, reporting, ingestion connectors, and agent orchestration from scratch would increase maintenance and correctness risk and delay the first complete, validated research experiment. On the other hand, adopting a framework without checking point-in-time availability, survivorship, data provenance, cost/fill semantics, or research holdout controls could give misleading financial results.

## Decision

**Reuse proven, appropriately licensed software by default, and write custom code only where a documented requirement is unmet, a narrow adapter is needed, or independent control is essential.** Every new substantive subsystem requires a build-versus-reuse record before implementation.

1. **Adopt** a maintained library/framework where it passes our acceptance tests and licensing/operational review.
2. **Wrap/adapt** external components behind narrowly scoped interfaces for data, simulation, research, and analysis. Avoid speculative universal abstraction layers.
3. **Build** the minimum project-specific behavior that cannot safely or effectively be delegated: point-in-time eligibility and provenance contracts; historical security/universe semantics where required; dataset/run lineage; holdout governance; bounded research orchestration; independent deterministic risk and trade authorization policies.
4. **Defer** paper/live brokerage connectivity, alternative data, elaborate dashboards, and infrastructure without a demonstrated research need.
5. **Retain** existing temporal validators, revision/listing/universe primitives, raw archive/receipts, tests, and evidence while evaluating alternatives. Existing implementations are not automatically permanent; replace or simplify only after equivalence and migration tests, with a documented preservation/migration decision. Sunk cost is not a reason to retain code.

### Candidate directions (not selected dependencies)

- **Primary research/backtest engine:** Evaluate [Microsoft Qlib](https://github.com/microsoft/qlib) first for research workflow and ML integration, against [QuantConnect LEAN](https://github.com/QuantConnect/Lean) for realistic event-driven order execution. Pick **one primary engine** for the first vertical slice; do not combine both by default. [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) or other engines are fallback candidates only if documented requirements fail.
- **Data and storage:** Evaluate [DuckDB](https://duckdb.org/) and Parquet for curated analytical datasets, [OpenBB](https://github.com/openbq-org/OpenBB) or direct provider adapters for licensed market/fundamental data, and official sources such as [SEC EDGAR](https://www.sec.gov/about/developer-resources) and [FRED](https://fred.stlouisfed.org/docs/api/fred/) when later milestones require them. Market data quality, historical coverage, access entitlements, adjustment conventions, and redistribution rights require separate validation.
- **Research support:** Evaluate existing libraries for features, ML, statistics, optimization, experiment tracking (for example MLflow), and performance analytics rather than rebuilding them. Evaluate [RD-Agent](https://github.com/microsoft/RD-Agent) **after** a deterministic non-agent baseline and holdout protocol are working.
- **Execution:** If later authorized, prefer an official broker SDK/adapter, but never delegate independent risk veto, account reconciliation requirements, manual kill switch, or trade authorization to an AI agent or untrusted plugin.

No package is adopted merely by being listed here. The dependency register and evaluation gates are in [dependency evaluation](../dependency-evaluation.md).

### Requirements that external frameworks must not weaken

- No future-data leakage: distinguish event, publication/source availability, ingestion/processing, and decision time; respect eligible revisions and derived-model lineage.
- No survivorship bias: retain historical identity, delistings, and point-in-time universe membership.
- Auditable economics: explicit fill timing, partial fills where relevant, spreads/slippage/fees, corporate actions, and cash/position accounting with independently checked reference fixtures.
- Reproducibility: pin dataset snapshot, code revision, strategy parameters, engine/package/container/environment version, seeds, and records of both successful and unsuccessful experiments.
- Valid research: chronological splits, controlled holdouts, multiple-testing disclosure and cost sensitivity; no backtest P&L asserted as evidence of edge.
- Safe boundaries: a historical engine cannot authorize paper/live orders; research agents cannot own broker credentials or bypass independently enforced risk constraints.
- Engineering: inspect maintenance and security posture, tested Python 3.11.17/macOS/Linux compatibility (or a deliberate isolation plan), license and dependency obligations, upgrade and exit paths.

### Evaluation before adoption

Write a brief decision record and repeatable spike for the highest-ranked candidates. Test the **same** licensed dataset and baseline strategy, with reference expected ledger outcomes and adversarial fixtures for future data, revised observations, delisting, split/dividend, execution timing, costs and missing/ambiguous data. Measure setup complexity, results, resource use, and upgrade/deployment constraints. Independently review discrepancies. Prefer the smallest dependency set that passes.

A passing smoke test or attractive benchmark is **not** approval of financial correctness, licensing, production safety, or a strategy's profitability. Dependencies must be pinned and added via the repository's approved lock/update procedure only after review. Keep the in-house point-in-time validation as a gate or independent check until the selected framework demonstrably preserves its behavior.

## Consequences

**Benefits:** faster end-to-end experiments, less duplicative code and accounting risk, use of established ecosystems, more effort on differentiated research.

**Costs/risks:** integration friction, external breaking changes, hidden framework assumptions, licensing constraints, supply-chain exposure, data-provider limitations, and possible complexity from overlapping frameworks. Mitigate with a dependency register, pinned versions, narrow adapters, integration/contract tests, documented exit paths, and active maintenance review.

## Impact on earlier roadmap

M1 remains active and its gates remain open. Before expanding M1 implementation, inventory existing primitives against candidate providers/storage and stop speculative archive growth. Insert an evidence-based dependency evaluation before M2–M4 implementation. Rewrite M2 as **adopt/integrate and validate simulation**, not **build our own engine**; rewrite M3/M4 as reuse-first experiments and bounded agent evaluation. Do not represent any of those milestones as complete until their original correctness gates pass.

## Sources to check during evaluation

- [Qlib source and package metadata](https://github.com/microsoft/qlib)
- [LEAN source and license](https://github.com/QuantConnect/Lean)
- [RD-Agent source and license](https://github.com/microsoft/RD-Agent)
- [OpenBB source and provider extensions](https://github.com/openbq-org/OpenBB)
- [DuckDB](https://duckdb.org/), [MLflow](https://github.com/mlflow/mlflow)
- [VectorBT license/terms](https://vectorbt.dev/terms/) (example of why source availability must not be mistaken for unrestricted commercial terms)

The candidate list is a research starting point, not legal advice or a permanent license inventory.
