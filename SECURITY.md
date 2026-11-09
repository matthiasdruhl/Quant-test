# Security and execution boundary

This repository begins with **no broker connection, no credentials, and no live trading**.

- Never commit tokens, passwords, private keys, licensed datasets, or real account identifiers.
- Keep local credentials in excluded environment files or a secret manager, never in AI prompts or logs.
- Review external data terms and usage restrictions before ingestion.
- Any future broker integration must separate paper/live credentials and require owner-approved activation.
- Future orders must pass a deterministic risk gate and be reconciled against broker truth.
- Report suspected security issues privately to the repository owner rather than committing secrets to a pull request.
