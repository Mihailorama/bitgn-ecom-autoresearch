**Proposed Isolated Next Experiment**

- **Target task shape:** deterministic `ge` inventory prompts handled by `_try_inventory_count` (`op == "ge"`) where at least one requested product resolves as `fallback_single` (not `exact_group`), i.e. the unstable `t16` class (`How many ... at least N ... today ... <COUNT|QTY>`).  
  Evidence basis: `_resolve_product_variant` + fallback path in [agent.py](/Users/m/code/mihailorama/bitgn-ecom-autoresearch/runs/2026-05-27-072337-codex53-smoke2/workspace/agent.py:1613), `ge` path in [agent.py](/Users/m/code/mihailorama/bitgn-ecom-autoresearch/runs/2026-05-27-072337-codex53-smoke2/workspace/agent.py:1991), and RED tests in [smoke_test.py](/Users/m/code/mihailorama/bitgn-ecom-autoresearch/runs/2026-05-27-072337-codex53-smoke2/workspace/smoke_test.py:813).

- **One isolated change:** add a **task-local fallback rescue branch** only for `ge` + `fallback_single`: if fallback product has `family_id`, probe same-family siblings and swap to a sibling candidate **only inside this branch** before `_build_inventory_refs`; do not alter exact-group logic or non-`ge` flow.  
  Keep diagnostics via existing `INVENTORY_DIAG` emission.

- **Evidence to collect:**
  1. RED->GREEN on both `t16` failure classes (missing required sibling ref + fallback overcount).
  2. `INVENTORY_DIAG` deltas: count of `fallback_single`, whether sibling swap happened, chosen SKU availability.
  3. `t16` stability sample (10 serial runs): pass rate and fail-type mix.
  4. Guardrail subset (`t13 t14 t15 t45`) and one full sweep solved-count.
  5. Security grep must stay clean.

- **Verifier commands (read-only proposal; commands to run after implementation):**
  1. `rtk uv run python -m py_compile agent.py llm.py && rtk uv run python smoke_test.py`
  2. `rtk uv run python -c "import smoke_test as s; s.test_red_t16_missing_required_ref_should_use_available_family_sibling()"`
  3. `rtk uv run python -c "import smoke_test as s; s.test_red_t16_count_mismatch_should_not_overcount_fallback_candidate()"`
  4. `rtk PARALLEL=1 MODEL_ID=codex:gpt-5.3-codex uv run python main.py t16` (repeat 10x, keep logs)
  5. `rtk PARALLEL=1 MODEL_ID=codex:gpt-5.3-codex uv run python main.py t13 t14 t15 t45`
  6. `rtk PARALLEL=6 MODEL_ID=codex:gpt-5.3-codex make sweep`
  7. `rtk rg "expected outcome OUTCOME_DENIED_SECURITY, got OUTCOME_OK" /tmp/sweep_logs/*.log`

- **Abort condition:** stop and revert experiment if any of these happen:
  1. either RED test remains failing,
  2. any new miss appears in `t13/t14/t15/t45`,
  3. full sweep solved-count drops below current accepted envelope (or introduces new non-`t16` failures),
  4. security grep returns any hit.