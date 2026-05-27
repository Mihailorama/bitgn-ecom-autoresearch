"""Small autoresearch-style runner for BitGN ECOM experiments.

The runner keeps the main benchmark repo untouched by copying it into a per-run
workspace, asking Codex CLI for a proposal or patch, then running verifier
commands inside that workspace. It is intentionally conservative: default mode
is read-only proposal generation.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_IGNORES = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".antigravitycli",
    "artifacts",
}


@dataclass
class Experiment:
    name: str
    model: str
    target_repo: Path
    task: str
    out_dir: Path
    allow_edit: bool = False
    timeout_seconds: int = 300


def build_codex_command(model: str, repo: Path, prompt: str, output: Path, allow_edit: bool = False) -> list[str]:
    sandbox = "workspace-write" if allow_edit else "read-only"
    return [
        "codex",
        "exec",
        "-m",
        model,
        "--sandbox",
        sandbox,
        "-C",
        str(repo.resolve()),
        "--output-last-message",
        str(output.resolve()),
        prompt,
    ]


def write_experiment_files(exp: Experiment) -> None:
    exp.out_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        **asdict(exp),
        "target_repo": str(exp.target_repo),
        "out_dir": str(exp.out_dir),
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    (exp.out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    (exp.out_dir / "prompt.md").write_text(exp.task.rstrip() + "\n", encoding="utf-8")


def copy_workspace(target_repo: Path, workspace: Path) -> None:
    if workspace.exists():
        shutil.rmtree(workspace)

    def ignore(_dir: str, names: list[str]) -> set[str]:
        return {name for name in names if name in DEFAULT_IGNORES}

    shutil.copytree(target_repo, workspace, ignore=ignore)


def run_command(command: list[str], cwd: Path, timeout_seconds: int) -> dict[str, object]:
    started = time.time()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "elapsed_seconds": round(time.time() - started, 3),
            "output": completed.stdout,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "returncode": None,
            "elapsed_seconds": round(time.time() - started, 3),
            "output": exc.stdout or "",
            "timed_out": True,
        }


def run_experiment(exp: Experiment, verify_cmds: list[str]) -> int:
    write_experiment_files(exp)
    workspace = (exp.out_dir / "workspace").resolve()
    copy_workspace(exp.target_repo, workspace)

    last_message = exp.out_dir / "codex_last_message.md"
    codex_cmd = build_codex_command(
        model=exp.model,
        repo=workspace,
        prompt=exp.task,
        output=last_message,
        allow_edit=exp.allow_edit,
    )
    codex_result = run_command(codex_cmd, workspace, exp.timeout_seconds)
    (exp.out_dir / "codex_result.json").write_text(
        json.dumps(codex_result, indent=2) + "\n",
        encoding="utf-8",
    )

    verify_results = []
    for verify_cmd in verify_cmds:
        verify_results.append(
            run_command(["/bin/zsh", "-lc", verify_cmd], workspace, exp.timeout_seconds)
        )
    (exp.out_dir / "verify_results.json").write_text(
        json.dumps(verify_results, indent=2) + "\n",
        encoding="utf-8",
    )

    summary = [
        "# Autoresearch Experiment",
        "",
        f"- name: `{exp.name}`",
        f"- model: `{exp.model}`",
        f"- target_repo: `{exp.target_repo}`",
        f"- workspace: `{workspace}`",
        f"- allow_edit: `{exp.allow_edit}`",
        f"- codex_returncode: `{codex_result['returncode']}`",
        f"- codex_timed_out: `{codex_result['timed_out']}`",
        "",
        "| verifier | returncode | timed_out | elapsed |",
        "|---|---:|---:|---:|",
    ]
    for item in verify_results:
        summary.append(
            f"| `{item['command'][-1]}` | {item['returncode']} | {item['timed_out']} | {item['elapsed_seconds']}s |"
        )
    (exp.out_dir / "SUMMARY.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    if codex_result["returncode"] != 0:
        return 1
    if any(item["returncode"] != 0 or item["timed_out"] for item in verify_results):
        return 1
    return 0


def default_out_dir(name: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    return Path("runs") / f"{stamp}-{name}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-repo", type=Path, default=Path("../bitgn-ecom-agent"))
    parser.add_argument("--model", default="gpt-5.3-codex")
    parser.add_argument("--name", default="bitgn-proposal")
    parser.add_argument("--task", default=None)
    parser.add_argument("--task-file", type=Path, default=Path("program.md"))
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--allow-edit", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--verify-cmd", action="append", default=[])
    args = parser.parse_args(argv)

    task = args.task
    if task is None:
        task = args.task_file.read_text(encoding="utf-8")
    out_dir = args.out_dir or default_out_dir(args.name)
    exp = Experiment(
        name=args.name,
        model=args.model,
        target_repo=args.target_repo.resolve(),
        task=task,
        out_dir=out_dir,
        allow_edit=args.allow_edit,
        timeout_seconds=args.timeout_seconds,
    )
    return run_experiment(exp, args.verify_cmd)


if __name__ == "__main__":
    raise SystemExit(main())
