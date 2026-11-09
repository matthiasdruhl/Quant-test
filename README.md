# Quant Test

A long-term, **research-first** quantitative equities platform. Initial focus: reproducible U.S. stock swing-trading research, not live trading.

> **Status:** Architecture and foundational scaffolding only. No trading strategy, backtesting engine, brokerage integration, or live execution is implemented. Nothing here establishes a profitable trading edge.

## Design priorities

1. **Point-in-time correctness** — no future information or survivorship bias.
2. **Reproducibility** — fixed data versions, code revisions, configurations, and seeds.
3. **Independent verification** — reference fixtures and adversarial tests, not just agent-written assertions.
4. **Separation of authority** — AI research code can never approve broker orders.
5. **Minimal complexity** — one modular Python package; no event bus or microservices until justified.

## Roadmap

0. Contracts, governance, and CI
1. Historical data and security master
2. Backtesting and accounting
3. Strategy baselines and statistical evaluation
4. Codex/Claude research agents
5. Macroeconomic and verified event intelligence
6. Insider, 13F, and public financial disclosure intelligence
7. Paper execution, reconciliation, and independent risk gates
8. Alternative data (satellite imagery is a later experiment)
9. Controlled deployment and portfolio monitoring

See [roadmap](docs/roadmap.md), [architecture](docs/architecture.md), [invariants](docs/invariants.md), and [AGENTS.md](AGENTS.md).

## Repository layout

```text
src/quant_test/
  core/          # Time, identifiers, common contracts
  data/          # Historical data, actions, lineage
  research/      # Features, experiment registry, evaluation
  backtest/      # Simulation and accounting
  strategies/    # Pure strategy implementations
  intelligence/  # Macro, filings, news, alternative data
  portfolio/     # Allocation and risk decisions
  execution/     # Paper/live broker adapters, later
tests/
  unit/          # Fast, deterministic tests
  integration/   # Module boundary tests
  contract/      # Reference cases and invariants
  fixtures/      # Small curated inputs
docs/decisions/  # Architecture decision records
```

## Local development

Use Python 3.11 or newer:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
ruff check .
ruff format --check .
mypy src
pytest
```

CI runs the same checks. This skeleton contains only one implemented foundational contract: timestamp availability semantics; no trading functionality.

## Safety and scope

- Live trading is **not implemented** and must not be added without an explicit design and authorization review.
- Never commit API keys, brokerage credentials, or proprietary datasets.
- Data vendors' licenses and applicable securities regulations must be reviewed before collection or trading.
- Published disclosures are not contemporaneous holdings: historical features must use **when information was available**, not when an underlying trade occurred.

This is software research infrastructure, not investment advice.
