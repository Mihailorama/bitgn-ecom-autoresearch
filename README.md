# BitGN ECOM Autoresearch Runner

Local private experiment harness inspired by `karpathy/autoresearch`.

The runner does not edit the main `bitgn-ecom-agent` repo directly. It copies the
target repo into a per-run workspace, invokes Codex CLI, stores the model output,
then runs explicit verifier commands in that copied workspace.

Default mode is read-only proposal generation:

```sh
python3 autoresearch_runner.py \
  --target-repo ../bitgn-ecom-agent \
  --model gpt-5.3-codex \
  --timeout-seconds 180 \
  --verify-cmd 'uv run python -m py_compile agent.py llm.py run_parallel.py'
```

Use `--allow-edit` only for a deliberate experiment branch. Even then, changes
remain inside `runs/<experiment>/workspace` until manually reviewed.
