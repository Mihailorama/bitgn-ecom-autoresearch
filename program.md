# BitGN ECOM Autoresearch Program

You are an autonomous researcher working in this repo only:

`/Users/m/code/mihailorama/bitgn-ecom-autoresearch`

This repo follows `karpathy/autoresearch` as a process template:

- one fixed evaluator: `evaluator.py`
- one editable experiment file: `agent.py`
- one human-authored research program: this file
- one scalar objective: perfect tasks per current `bitgn/ecom1-dev` run
- one append-only ledger: `results.tsv`

## Non-Negotiable Boundary

Do not copy code from `/Users/m/code/mihailorama/bitgn-ecom-agent`.

That neighboring repo may be read only for historical evidence such as task
instructions, score details, and observed BitGN platform behavior. The platform
changes over time, so treat that evidence as stale unless current live runs
confirm it.

When implementing or reviewing this repo's `agent.py`, do not open the
neighboring repo's `agent.py`, `llm.py`, `main.py`, or `run_parallel.py`. Work
from:

- current repo code;
- official BitGN SDK interfaces;
- fresh live samples under this repo's `runs/`;
- runtime schema/records observed through the current BitGN VM.

## What You May Change

- `agent.py`
- tests that describe the independent algorithm's behavior
- this `program.md`, when improving the research organization

## What You Must Not Change

- `evaluator.py` scoring semantics
- BitGN control-plane behavior
- `/Users/m/code/mihailorama/bitgn-ecom-agent`
- benchmark-specific hardcoded answers that only fit one observed run
- security behavior that turns a denial into false success

## Objective

Maximize perfect task count on the current `bitgn/ecom1-dev` benchmark. The
target is `N/N`, where `N` is the live task count returned by BitGN at the start
of that run.

Keep/discard:

1. Reject any security regression.
2. Keep if perfect count increases.
3. After current `N/N`, keep the faster wall time only when the task-id set is
   identical.
4. Otherwise discard.

## Loop

1. Probe the live benchmark task count and task ids.
2. Read `results.tsv` and the latest run summary for the same task-id set.
3. Pick one failing task id or small related group.
4. Run repeated samples for that task id or group to observe randomized variants.
5. Inspect only enough historical logs to classify the failure distribution.
6. Write a narrow offline test for the intended behavior.
7. Mutate `agent.py` behind a narrow predicate.
8. Run `make test`.
9. Run targeted live validation for target, neighbor, and security sentinel
   samples.
10. Run full live sweep.
11. Record the result and keep only if it improves the scalar objective for the
    same live task-id set.

## Sampling Rules

- Treat each task id as a distribution of variants.
- Never accept a fix from one lucky target pass.
- Before a fix, sample the failing id enough times to identify common formats,
  tools, policies, and failure modes.
- After a fix, run target samples plus neighbors that share answer format,
  runtime tools, policy surface, or historical regression risk.
- Use clusters to choose regression samples, not to justify broad code changes.

Generation 0 is intentionally minimal. Build the algorithm here from first
principles and current BitGN observations.

## Current Capability Notes

As of 2026-05-27, this repo contains two live-observed task capabilities:

- `t49` is the first accepted target capability. The agent must keep treating
  SQL workaround files and catalogue reporting updates as dynamic VM evidence,
  not as stable hardcoded paths. The latest targeted validation was `12/12`
  perfect.
- `t50` is an active partial capability. It resolves current identity, newest
  active basket, policy refs, and basket refs, but still needs more repeated
  validation before it can be accepted. The latest targeted validation was
  `9/12` perfect, with remaining false negatives on checkout eligibility.

Next research priority:

1. Stabilize `t50` without weakening security or forcing checkout when the
   live policy/tooling says unsupported.
2. Re-run `t49 t50` together to detect cross-task regression.
3. Only then move to the next independent cluster, likely `t15` product
   availability counting or `t48` archive fraud TSV totals.
