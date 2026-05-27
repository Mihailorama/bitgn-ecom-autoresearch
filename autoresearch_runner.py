"""Karpathy-style orchestration utilities for the BitGN autoresearch track.

This file is deliberately infrastructure, not the BitGN agent. The editable
experiment surface is `agent.py`; the fixed live evaluator is `evaluator.py`;
`program.md` is the human-authored research program.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
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
    "experiments",
    "results.tsv",
    "runs",
    "worktrees",
    ".worktrees",
}

EDITABLE_EXPERIMENT_FILES = ("agent.py",)
FIXED_EVALUATOR_FILES = ("evaluator.py", "autoresearch_runner.py")


@dataclass(frozen=True)
class Score:
    perfect: int
    total: int
    wall_seconds: int
    failed_tasks: list[str]
    security_regression: bool
    task_ids: tuple[str, ...] = ()


@dataclass
class Experiment:
    name: str
    model: str
    target_repo: Path
    task: str
    out_dir: Path
    allow_edit: bool = False
    timeout_seconds: int = 300


def parse_sweep_summary(log_text: str) -> Score:
    final = re.search(r"FINAL:\s+[\d.]+%\s+\((\d+)/(\d+) perfect", log_text)
    if not final:
        raise ValueError("could not find FINAL score line")
    speed = re.search(r"SPEED:\s+wall\s+(\d+)s", log_text)
    failed_tasks = []
    task_ids = []
    for line in log_text.splitlines():
        match = re.match(r"^(t\d+):\s+([0-9.]+|ERROR)\b", line.strip())
        if not match:
            continue
        task_id, raw_score = match.groups()
        task_ids.append(task_id)
        if raw_score == "ERROR" or float(raw_score) < 0.999:
            failed_tasks.append(task_id)
    return Score(
        perfect=int(final.group(1)),
        total=int(final.group(2)),
        wall_seconds=int(speed.group(1)) if speed else 0,
        failed_tasks=failed_tasks,
        security_regression="expected outcome OUTCOME_DENIED_SECURITY, got OUTCOME_OK" in log_text,
        task_ids=tuple(sorted(task_ids)),
    )


def task_ids_hash(task_ids: list[str] | tuple[str, ...]) -> str:
    normalized = "\n".join(sorted(task_ids))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def same_task_set(baseline: Score, candidate: Score) -> bool:
    return baseline.task_ids == candidate.task_ids and baseline.total == candidate.total


def should_keep_candidate(baseline: Score, candidate: Score) -> bool:
    if candidate.security_regression:
        return False
    if not same_task_set(baseline, candidate):
        return False
    if candidate.perfect > baseline.perfect:
        return True
    if candidate.perfect < baseline.perfect:
        return False
    if candidate.perfect == candidate.total == baseline.perfect == baseline.total:
        return candidate.wall_seconds > 0 and candidate.wall_seconds < baseline.wall_seconds
    return False


def _tsv_cell(value: object) -> str:
    return str(value).replace("\t", " ").replace("\n", " ").strip()


def append_result_row(path: Path, commit: str, score: Score, status: str, description: str) -> None:
    header = "commit\tperfect\ttotal\ttask_ids_hash\twall_seconds\tstatus\tfailed_tasks\tdescription\n"
    if not path.exists():
        path.write_text(header, encoding="utf-8")
    row = [
        commit,
        score.perfect,
        score.total,
        task_ids_hash(score.task_ids),
        score.wall_seconds,
        status,
        ",".join(score.failed_tasks),
        description,
    ]
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\t".join(_tsv_cell(item) for item in row) + "\n")


def record_candidate_decision(
    baseline_log: Path,
    candidate_log: Path,
    ledger_path: Path,
    commit: str,
    description: str,
) -> str:
    baseline = parse_sweep_summary(baseline_log.read_text(encoding="utf-8"))
    candidate = parse_sweep_summary(candidate_log.read_text(encoding="utf-8"))
    if not same_task_set(baseline, candidate):
        status = "new_baseline_required"
    else:
        status = "keep" if should_keep_candidate(baseline, candidate) else "discard"
    append_result_row(ledger_path, commit=commit, score=candidate, status=status, description=description)
    return status


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


def build_eval_command(tasks: list[str], model: str, parallel: int, log_dir: Path) -> list[str]:
    return [
        "python3",
        "evaluator.py",
        "--model",
        model,
        "--parallel",
        str(parallel),
        "--log-dir",
        str(log_dir),
        *tasks,
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
    parser.add_argument("--score-log", type=Path, default=None, help="parse an evaluator log and append to results.tsv")
    parser.add_argument("--baseline-log", type=Path, default=None, help="compare --score-log against this baseline log")
    parser.add_argument("--score-status", default="keep")
    parser.add_argument("--score-description", default="")
    parser.add_argument("--score-commit", default="unknown")
    parser.add_argument("--target-repo", type=Path, default=Path("."))
    parser.add_argument("--model", default="gpt-5.3-codex")
    parser.add_argument("--name", default="bitgn-proposal")
    parser.add_argument("--task", default=None)
    parser.add_argument("--task-file", type=Path, default=Path("program.md"))
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--allow-edit", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--verify-cmd", action="append", default=[])
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent
    if args.score_log is not None:
        ledger_path = repo_root / "results.tsv"
        if args.baseline_log is not None:
            status = record_candidate_decision(
                args.baseline_log,
                args.score_log,
                ledger_path,
                commit=args.score_commit,
                description=args.score_description,
            )
            print(f"decision: {status}")
        else:
            score = parse_sweep_summary(args.score_log.read_text(encoding="utf-8"))
            append_result_row(
                ledger_path,
                commit=args.score_commit,
                score=score,
                status=args.score_status,
                description=args.score_description,
            )
            print(f"score: {score.perfect}/{score.total} perfect, wall {score.wall_seconds}s")
        return 0

    task = args.task or args.task_file.read_text(encoding="utf-8")
    exp = Experiment(
        name=args.name,
        model=args.model,
        target_repo=args.target_repo.resolve(),
        task=task,
        out_dir=args.out_dir or default_out_dir(args.name),
        allow_edit=args.allow_edit,
        timeout_seconds=args.timeout_seconds,
    )
    return run_experiment(exp, args.verify_cmd)


if __name__ == "__main__":
    raise SystemExit(main())
