# Agentic development graph (proposal)

This is a **development workflow**, not an application runtime agent. Apply on a feature branch; never merge or deploy automatically. Existing repository instructions, architecture decisions, data/security contracts and CI remain authoritative. Start with a single agent plus tests; use a graph only when independent work exists.

## Execution graph

```text
intake -> plan/acceptance criteria -> independent test-design
                                  -> [builder A, builder B ...] (only independent, isolated changes)
                                  -> verify (deterministic commands, record exit codes)
                                  -> [PASS -> independent review -> merge-ready PR]
                                  -> [FAIL -> classify failure -> targeted repair -> verify]
                                  -> [UNRESOLVED -> stop and surface evidence]
```

A task node has: id, objective, dependencies, input commit SHA, allowed paths, disallowed changes, acceptance criteria, verification commands, max repair attempts, produced artifacts, and status. Statuses: blocked, ready, running, verifying, repair, review, passed, failed. A downstream node runs only after all parent nodes have passed. Independent builders use separate worktrees/branches and never edit the same files concurrently. Integrate only after successful verification of the combined diff.

## Roles

- **Planner:** inspect repository, extract hard constraints, make a small directed acyclic task graph; specify precise tests and non-goals.
- **Test designer:** independently author adversarial/regression cases from requirements, not the builder's output; fail before the implementation when practical.
- **Builder:** implement one node with minimal changes, no scope creep.
- **Verifier:** run the repository's actual commands (not invented results), record command, exit code, revision, and failure output. Do not silently skip expensive or unavailable checks.
- **Repair agent:** classify the smallest root cause and patch it, without weakening assertions or bypassing safeguards; at most **3** attempts per failing node, then escalate.
- **Independent reviewer:** use a fresh context/different agent from the builder to scrutinize invariants, security, test independence and unexpected changes. Reviewer can reject and reopen a node.

## Loop and stop conditions

1. Pin the base SHA, inspect repository instructions and CI. For every node record preconditions, acceptance checks, and a rollback path.
2. Execute only ready nodes. Prefer serial execution when shared code/contracts would make parallel work unsafe.
3. Verify after each implementation or repair. Save a compact evidence report with attempted checks, skipped gates and reasons, failing test names, and diff paths.
4. On failure: distinguish product defect, test defect, environment issue or flaky test. Require evidence for reclassification. Never edit a test merely to turn it green.
5. After three unsuccessful repair attempts, changed requirements, security violations, missing credentials/dependencies, or uncertain data rights: stop and ask for human intervention. No infinite self-improvement loops.
6. Independently review the verified combined diff. A reviewer cannot approve their own implementation.
7. Open a PR with graph/task summary, actual command results, unresolved risks and links to CI. **Humans decide merge and release.**

## What this does and does not automate

Existing CI is the external verification gate. This document defines the agent instructions/task DAG but does not launch autonomous agents on GitHub, install a runner, or make background work happen. An execution adapter (for example, a locally supervised Codex CLI runner) requires a separate reviewed change with explicit credentials, rate/cost limits, process isolation, and cancellation controls.

## Quant-specific gates

- Follow `AGENTS.md`, `docs/invariants.md`, `docs/testing-strategy.md`, `docs/decisions/0020-open-source-first-dependency-strategy.md` and `docs/dependency-evaluation.md`.
- Mandatory checks: `ruff check .`, `ruff format --check .`, `mypy src`, `pytest`; installed-wheel/offline and OS-matrix proofs belong to hosted CI.
- The test designer must explicitly try look-ahead leakage, revised historical data, delistings/survivorship, corporate actions, fill/cost convention mistakes and contaminated holdouts when relevant.
- Quant graph: data contracts -> independently computed fixture -> implementation -> deterministic tests -> temporal/accounting adversarial review -> CI -> PR. Engine comparisons (Qlib versus LEAN) remain **evaluation only** until the dependency gate is approved.
- Never autonomously run live orders, create brokerage accounts, select/promote strategies, claim profitability, or loosen reference fixtures.
