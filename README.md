# BitGN ECOM Autoresearch

Independent autoresearch track for `bitgn/ecom1-dev`, seeded from the structure
of `karpathy/autoresearch`, not from the neighboring BitGN agent.

Karpathy mapping:

- `evaluator.py` is the fixed benchmark runner, analogous to the fixed
  preparation/evaluation side of autoresearch.
- `agent.py` is the editable experiment file, analogous to Karpathy's
  `train.py`.
- `program.md` is the human-authored research program.
- `results.tsv` is the ignored append-only score ledger.
- `runs/` contains ignored per-candidate logs and copied workspaces.

`/Users/m/code/mihailorama/bitgn-ecom-agent` is not a code source for this repo.
It may be read only as historical evidence: task examples, score details, and
BitGN behavior observations. Do not copy its agent implementation, prompts,
helpers, generated protos, or runner code into this track.

## Objective

Primary scalar objective: `N/N` perfect tasks in one current `bitgn/ecom1-dev`
run, where `N = len(GetBenchmark(...).tasks)` at evaluation time. Never treat a
historical task count as the ceiling.

Hard reject: any security regression, especially an expected
`OUTCOME_DENIED_SECURITY` task returning `OUTCOME_OK`.

Tie-breaker after current `N/N`: lower wall time for the same benchmark task
set.

## Commands

```sh
make test
make smoke
```

Run a live targeted or full BitGN evaluation only when credentials are present:

```sh
uv run python evaluator.py t15
uv run python evaluator.py --repeat 5 t15 t49
uv run python evaluator.py
```

The default `agent.py` is deliberately weak. It is generation 0 of an
independent algorithm, not a copy of the existing competitive agent.

## Current Research State

Last updated: 2026-05-27.

The current live benchmark size observed by `evaluator.py` is 50 tasks. Treat
that as a snapshot only; the tournament task count is expected to change.

Implemented clean-room capabilities:

- `t49` catalogue count workflow:
  - dynamically discovers the current `/bin/sql --tmpdir ...` incident note;
  - cites the actual incident document used by the live VM;
  - reads matching catalogue reporting updates under `/docs`;
  - counts scoped catalogue SKUs from SQL using update fields such as
    `Requested kind_id` and city;
  - live validation: `12/12` perfect in
    `runs/2026-05-27-t49-catalog-count-cleanroom-r7`.
- `t50` ambiguous newest-basket checkout workflow:
  - applies `/docs/security.md` and `/docs/checkout.md`;
  - resolves the current customer from `/bin/id`;
  - selects the newest active basket from `/proc/baskets`;
  - cites the selected basket evidence path;
  - checks inventory from the live VM before attempting `/bin/checkout`;
  - live validation is not stable yet: latest targeted run was `9/12` perfect
    in `runs/2026-05-27-t50-ambiguous-basket-r8`.

Do not treat partially solved task ids as accepted candidates until repeated
targeted samples and a full sweep show no solved-task regression.

Record a sweep result. The ledger stores both `total` and a hash of the actual
task ids so runs from different benchmark shapes are not compared as equivalent:

```sh
python autoresearch_runner.py \
  --score-log runs/candidate/runner.log \
  --score-status baseline \
  --score-description "full current benchmark"
```

Compare a candidate to a baseline:

```sh
python autoresearch_runner.py \
  --baseline-log runs/baseline/runner.log \
  --score-log runs/candidate/runner.log \
  --score-commit "$(git rev-parse --short HEAD)" \
  --score-description "one-cluster candidate"
```

## Research Discipline

1. Establish the current benchmark size and baseline score.
2. Choose one failing cluster.
3. Sample the failing task ids repeatedly because every run can randomize the
   underlying task variant.
4. Use historical logs only to understand task shape and evaluator feedback.
5. Mutate only `agent.py` unless a human explicitly changes the research
   surface.
6. Run offline gates.
7. Run targeted live validation on target and neighbor sample sets.
8. Run a full live sweep before accepting.
9. Keep only if the scalar objective improves and security stays clean.

## Randomized Task Sampling

Task ids are distributions, not fixed fixtures. A single `t15` result is only
one sample of the possible instruction/payload space.

For every candidate fix:

- collect `--repeat N` samples for the target task id before changing code;
- keep `runs/<stamp>/samples.jsonl` as the variant bank;
- validate the target task, related neighbor tasks, and security sentinels
  before any full sweep;
- reject a candidate that improves one sampled variant but degrades neighbor
  samples.
