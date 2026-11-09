# Experiment registration and holdout protocol (design contract)

This specifies M3 acceptance requirements. No experiment registry, access-control service, or strategy promotion implementation exists in the scaffold.

## Attempt record
Register an immutable attempt ID before running a hypothesis/configuration or reading evaluation outcomes. Record a study/family ID, hypothesis and parent attempt, owner, creation time, code revision and clean-tree status, configuration hash, data snapshot IDs, feature/artifact lineage, environment manifest/hash, seeds, split definitions, benchmark, cost/capacity assumptions, and the intended metrics and selection rule. Periods use explicit timezone-aware half-open intervals. Changes to code, data, configuration, selection rules, or fitted artifacts create a new attempt linked to the earlier one.

Append status events for registered, running, completed, failed, or aborted attempts, with timestamps, outputs/checksums and error reasons. A failed or unpromising attempt is never deleted or reused. Record infrastructure retries as child executions under the same frozen attempt and count them separately from distinct hypotheses/configurations. Reports disclose both counts, the study/family boundary, and all prior selection steps, including manual or agent-assisted exploration. Metadata corrections append a superseding event rather than rewriting history.

## Holdout lifecycle
1. **Sealed:** designate a named holdout with immutable snapshot IDs, instruments/universe, interval, label horizon, and owner before strategy selection. Keep labels and holdout outcomes unavailable to exploratory workers. Choose chronological training/validation partitions, purging/embargo where needed, and the study's selection/multiple-comparison policy using development data.
2. **Reserved:** record owner/reviewer approval of a frozen candidate, code/config/artifact/environment hashes, benchmark/cost assumptions, metrics, acceptance criteria, and permitted evaluation count. A reservation can be released only with auditable proof that no holdout read occurred.
3. **Consumed:** atomically persist consumption and attempt ID **before** granting any holdout read, export, chart, or metric access. Concurrent attempts cannot obtain the same sealed reservation. If consumption cannot be persisted, access fails closed. Exceptions, timeouts, disappointing results, partial reads, and infrastructure retries do not restore untouched status.
4. **Retired from selection:** append evaluation outcomes and approval/rejection evidence. The consumed period may support a clearly labeled rerun or diagnostic report of the frozen candidate, but cannot select a replacement or tuned strategy as though it were untouched. A later candidate needs a newly sealed, previously unexamined evaluation period; if none exists, promotion waits for new forward evidence.

Owner approval does not turn a consumed period back into an untouched holdout. If accidental access occurs while sealed/reserved, record a breach and consume the affected period. Overlapping periods or snapshots carrying the same previously inspected outcomes are not fresh holdouts. Walk-forward evaluation may use preregistered chronological folds, but every prediction must be recorded before its corresponding outcome is available and no fold may silently become reusable selection data.

## Acceptance evidence before M3 completion
- Independent tests show failures and infrastructure retries remain recorded and hypothesis/execution counts are reproducible.
- Concurrent access, failed consumption writes, partial reads, and attempts to reset consumed state fail closed.
- Boundary fixtures cover label overlap, chronological splits, revisions, and future-trained model/preprocessor leakage.
- Reports include baseline/after-cost results, uncertainty, all selection counts, environment and source IDs, holdout status, and independent review evidence.

Storage and access enforcement must be designed and reviewed when M3 is implemented. This document is not evidence that a database or sealed dataset already exists.
