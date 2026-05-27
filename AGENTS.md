# Repository Guidelines

@/Users/m/.codex/RTK.md

This repository is the standalone BitGN ECOM autoresearch track, seeded from
the structure of `karpathy/autoresearch`.

Clean-room boundary:
- Do not mutate `/Users/m/code/mihailorama/bitgn-ecom-agent`.
- Do not copy its agent code into this repo.
- Do not read `/Users/m/code/mihailorama/bitgn-ecom-agent/agent.py`,
  `llm.py`, `main.py`, or `run_parallel.py` while implementing or reviewing
  this repo's `agent.py`.
- Historical logs/artifacts from the neighboring repo may be read only when
  explicitly useful for understanding BitGN behavior; treat them as stale
  observations, not implementation templates.

The editable research target is this repo's `agent.py`. Treat `evaluator.py` as
the fixed evaluator unless the user explicitly asks to change evaluation
mechanics.

Before accepting any scoring candidate, run offline checks and compare against a
saved baseline. A security miss such as `expected outcome
OUTCOME_DENIED_SECURITY, got OUTCOME_OK` rejects the candidate regardless of
perfect count.
