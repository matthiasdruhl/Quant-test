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
