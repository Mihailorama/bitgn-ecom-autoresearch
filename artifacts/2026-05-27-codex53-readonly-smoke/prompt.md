# BitGN ECOM Autoresearch Program

You are running a single read-only research iteration for the BitGN ECOM agent.

Target repo: `/Users/m/code/mihailorama/bitgn-ecom-agent`
Model: `gpt-5.3-codex`

Task:
Read the current BitGN ECOM agent repo at a high level and propose one isolated next experiment for t16-style inventory/catalog reference failures. Do not edit files and do not run benchmarks.

Rules:
- Do not edit files.
- Do not run full benchmark sweeps.
- Read only the minimum repo context needed.
- Propose exactly one isolated experiment that can be validated with targeted tests.
- Explicitly list the likely affected task ids and the tasks that must remain unchanged.
- Return Markdown with these sections: Observation, Proposed Single Change, Validation, Stop Criteria.
