## Observation
- Current deterministic `ge` inventory flow already uses exact candidate groups, but `t16` still fails on missing required product refs even when count logic is close ([BENCHMARK_NOTES.md](/Users/m/code/mihailorama/bitgn-ecom-agent/BENCHMARK_NOTES.md:168), [BENCHMARK_NOTES.md](/Users/m/code/mihailorama/bitgn-ecom-agent/BENCHMARK_NOTES.md:227)).
- Notes explicitly say the unresolved class is “required sibling SKU exists in same `family_id`, but SQL candidate set does not expose it” and suggests family-directory sibling augmentation ([BENCHMARK_NOTES.md](/Users/m/code/mihailorama/bitgn-ecom-agent/BENCHMARK_NOTES.md:229)).
- In code, `_resolve_product_variant` only uses SQL-loaded candidates and falls back to a single SKU when exact props miss; no family-sibling augmentation exists yet ([agent.py](/Users/m/code/mihailorama/bitgn-ecom-agent/agent.py:1585), [agent.py](/Users/m/code/mihailorama/bitgn-ecom-agent/agent.py:1613)).
- There are already two `red_t16_*` tests encoding this failure mode, but they are not called from `main()` smoke execution ([smoke_test.py](/Users/m/code/mihailorama/bitgn-ecom-agent/smoke_test.py:863), [smoke_test.py](/Users/m/code/mihailorama/bitgn-ecom-agent/smoke_test.py:1136)).

## Proposed Single Change
Add **one resolver augmentation step** in `_resolve_product_variant` for `ge` inventory usage:
- When exact match is empty but fallback product exists with `family_id`, list/read sibling SKU JSONs in that family directory and append sibling candidates that pass line/model hints.
- Then keep existing `_build_inventory_refs` selection logic unchanged.

Likely affected task ids:
- `t16` (primary target)
- `t13-t15` (same deterministic single-store `ge` inventory class; should be rechecked as guards)

Tasks that must remain unchanged:
- `t01-t12` (catalog/product-check/count paths)
- `t17-t20`, `t33` (city/multi-location inventory path)
- `t21+` policy/security/discount/payment tasks, including `t45` low-stock `lt` branch

## Validation
Targeted tests only (no sweeps):
1. Activate and run `test_red_t16_missing_required_ref_should_use_available_family_sibling` as primary pass/fail gate ([smoke_test.py](/Users/m/code/mihailorama/bitgn-ecom-agent/smoke_test.py:812)).
2. Activate and run `test_red_t16_count_mismatch_should_not_overcount_fallback_candidate` as regression guard ([smoke_test.py](/Users/m/code/mihailorama/bitgn-ecom-agent/smoke_test.py:863)).
3. Re-run existing deterministic guard tests for `ge`/mixed behavior:
   - `test_inventory_solver_counts_available_exact_candidate_sibling_for_ge`
   - `test_inventory_solver_uses_exact_candidates_when_other_ge_specs_need_fallback`
   - `test_inventory_ref_policy_counts_one_available_sku_per_requested_product`

## Stop Criteria
- Stop and keep the experiment if both `red_t16_*` tests pass and all listed guard tests stay green.
- Stop and reject if either:
  - `red_t16_*` still fails, or
  - any guard test regresses (especially overcounting or wrong ref selection in `t13-t15`-style shapes).

