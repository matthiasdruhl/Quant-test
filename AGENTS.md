# Repository instructions for coding agents

Read `docs/architecture.md`, `docs/invariants.md`, `docs/data-contracts.md`, and the active milestone in `docs/roadmap.md` before changing code.

## Mission and priorities
Create a correct, auditable, reproducible quantitative equity research platform. Priorities: correctness > reproducibility > security > maintainability > extensibility > performance > velocity.

## Scope discipline
- Work on one narrowly scoped issue/task at a time. State non-goals.
- Inspect existing interfaces before editing. Never silently change public contracts.
- New dependencies, storage systems, services, or financial conventions require a documented rationale/ADR.
- Prefer a modular monolith. No microservices, message brokers, or speculative abstractions.
- No mock data, empty exception handlers, unimplemented code, or placeholder behavior presented as complete.
- If blocked, report exactly what is missing; do not invent successful outcomes.

## Open-source-first dependency policy
- Read [ADR 0012](docs/decisions/0012-open-source-first-dependency-strategy.md) and [dependency evaluation](docs/dependency-evaluation.md) before proposing a new implementation for backtesting, storage, analytics, research tooling, AI agents, or broker connectivity.
- First compare maintained and appropriately licensed open-source solutions. Record adopt/wrap/build/defer, concrete rejected alternatives, costs, test evidence, and exit/migration risks. Do not introduce dependencies based on popularity or undocumented assumptions.
- Do not create a bespoke backtesting engine by default or install Qlib, LEAN, RD-Agent, OpenBB, MLflow, or another candidate without the evidence-based selection gate and an approved dependency change.
- Preserve all implemented temporal, universe, archival, and contract tests until independently verified replacement parity, with a reviewed migration. Do not treat sunk implementation cost as a selection argument.
- Keep the first vertical slice non-agent and non-trading: lawful history -> eligible observations -> simple baseline -> independently checked simulation -> saved analysis.

## Finance and time safety
- Distinguish event time, publication time, source availability, ingestion time, and decision time.
- Never evaluate a strategy with information not available at decision time.
- Preserve delisted securities and point-in-time universe membership in evaluable datasets.
- Model costs, fills, financing, corporate actions, and other constraints explicitly.
- Do not change accounting conventions without an ADR and independent reference fixtures.
- Do not reuse an untouched holdout for repeated strategy selection.
- Record failed experiments and the number of hypotheses tried.

## Agents and execution
- LLM output is an untrusted hypothesis, not an order.
- No AI-driven automatic deployment, account creation, strategy promotion, or order execution.
- Live trading is out of scope. Never request, access, print, or commit brokerage credentials.
- A future risk engine must be independently enforced, fail closed, and have emergency stop / reconciliation behavior.

## Change procedure
1. Inspect files; present a brief plan and acceptance tests before large changes.
2. Implement the smallest correct vertical slice, with typed APIs and deterministic tests.
3. Exercise negative cases and cross-module invariants, including independent reference cases.
4. Run `ruff check .`, `ruff format --check .`, `mypy src`, and `pytest`.
5. Report commands actually run and outputs; never claim checks passed if not executed.
6. State modified paths, assumptions, unresolved issues, and evidence for every acceptance item.

## PR review
Reject changes with missing provenance, invented performance, unvalidated temporal joins, weakened tests, unjustified dependency growth, or executable trading paths lacking explicit authorization.
