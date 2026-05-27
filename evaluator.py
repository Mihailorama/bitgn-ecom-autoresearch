"""Fixed BitGN evaluator wrapper.

This module owns benchmark execution only. It starts BitGN trials, calls an
agent command with task context in environment variables, ends each trial, and
prints a stable summary that `autoresearch_runner.py` can parse.

The default generation-0 command is intentionally weak (`python agent.py`). A
research candidate may change `agent.py`, but should not tune this evaluator to
game the metric.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from bitgn.harness_connect import HarnessServiceClientSync
from bitgn.harness_pb2 import (
    EndTrialRequest,
    EvalPolicy,
    GetBenchmarkRequest,
    StartRunRequest,
    StartTrialRequest,
    StatusRequest,
    SubmitRunRequest,
)
from connectrpc.errors import ConnectError


@dataclass(frozen=True)
class TaskResult:
    task_id: str
    score: float | None
    detail: list[str]
    error: str | None
    seconds: float
    sample_index: int = 1
    instruction_hash: str = ""
    instruction: str = ""
    log_path: str = ""


def instruction_hash(instruction: str) -> str:
    return hashlib.sha256(instruction.encode("utf-8")).hexdigest()[:16]


def sample_log_path(log_dir: Path, task_id: str, sample_index: int, repeat: int) -> Path:
    if repeat == 1:
        return log_dir / f"{task_id}.log"
    return log_dir / f"{task_id}-r{sample_index:02d}.log"


def write_sample_record(path: Path, result: TaskResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "task_id": result.task_id,
        "sample_index": result.sample_index,
        "instruction_hash": result.instruction_hash,
        "score": result.score,
        "detail": result.detail,
        "error": result.error,
        "seconds": round(result.seconds, 3),
        "instruction": result.instruction,
        "log_path": result.log_path,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def retry_call(fn, attempts: int = 5):
    delay = 1.0
    for index in range(attempts):
        try:
            return fn()
        except ConnectError:
            if index == attempts - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 8.0)


def run_agent_command(command: str, task_id: str, harness_url: str, instruction: str, model: str, log_path: Path) -> None:
    env = os.environ.copy()
    env.update(
        {
            "BITGN_TASK_ID": task_id,
            "BITGN_HARNESS_URL": harness_url,
            "BITGN_INSTRUCTION": instruction,
            "MODEL_ID": model,
        }
    )
    completed = subprocess.run(
        command,
        shell=True,
        text=True,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    log_path.write_text(
        f"TASK {task_id} (model {model})\n"
        f"INSTRUCTION: {instruction}\n"
        f"{'-' * 80}\n"
        f"{completed.stdout}",
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"agent command exited {completed.returncode}")


def run_one(trial_id: str, task_filter: set[str], args: argparse.Namespace, sample_index: int) -> TaskResult:
    client = HarnessServiceClientSync(args.host)
    started = time.time()
    try:
        trial = retry_call(lambda: client.start_trial(StartTrialRequest(trial_id=trial_id)))
    except ConnectError as exc:
        return TaskResult(trial_id, None, [], f"start_trial: {exc.code} {exc.message}", 0.0, sample_index=sample_index)

    if task_filter and trial.task_id not in task_filter:
        try:
            retry_call(lambda: client.end_trial(EndTrialRequest(trial_id=trial.trial_id)))
        except ConnectError:
            pass
        return TaskResult(trial.task_id, None, [], "skip", 0.0, sample_index=sample_index)

    log_path = sample_log_path(Path(args.log_dir), trial.task_id, sample_index, args.repeat)
    error = None
    try:
        run_agent_command(args.agent_cmd, trial.task_id, trial.harness_url, trial.instruction, args.model, log_path)
    except Exception as exc:
        error = f"agent error: {exc!r}"[:240]
        log_path.write_text(
            f"TASK {trial.task_id} (model {args.model})\n"
            f"INSTRUCTION: {trial.instruction}\n"
            f"{'-' * 80}\n{error}\n",
            encoding="utf-8",
        )
    seconds = time.time() - started

    try:
        result = retry_call(lambda: client.end_trial(EndTrialRequest(trial_id=trial.trial_id)))
    except ConnectError as exc:
        return TaskResult(
            trial.task_id,
            None,
            [],
            f"end_trial: {exc.code} {exc.message}",
            seconds,
            sample_index=sample_index,
            instruction_hash=instruction_hash(trial.instruction),
            instruction=trial.instruction,
            log_path=str(log_path),
        )

    if error:
        return TaskResult(
            trial.task_id,
            None,
            [],
            error,
            seconds,
            sample_index=sample_index,
            instruction_hash=instruction_hash(trial.instruction),
            instruction=trial.instruction,
            log_path=str(log_path),
        )
    score = result.score if result.score_available else None
    return TaskResult(
        trial.task_id,
        score,
        list(result.score_detail),
        None,
        seconds,
        sample_index=sample_index,
        instruction_hash=instruction_hash(trial.instruction),
        instruction=trial.instruction,
        log_path=str(log_path),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tasks", nargs="*", help="optional task ids such as t15 t49")
    parser.add_argument("--benchmark-id", default=os.getenv("BENCH_ID") or os.getenv("BENCHMARK_ID") or "bitgn/ecom1-dev")
    parser.add_argument("--host", default=os.getenv("BITGN_HOST") or os.getenv("BENCHMARK_HOST") or "https://api.bitgn.com")
    parser.add_argument("--api-key", default=os.getenv("BITGN_API_KEY") or "")
    parser.add_argument("--model", default=os.getenv("MODEL_ID") or "codex:gpt-5.3-codex")
    parser.add_argument("--parallel", type=int, default=int(os.getenv("PARALLEL", "6")))
    parser.add_argument("--repeat", type=int, default=int(os.getenv("REPEAT", "1")))
    parser.add_argument("--log-dir", default=os.getenv("SWEEP_LOG_DIR", "runs/evaluator"))
    parser.add_argument("--agent-cmd", default=os.getenv("AGENT_CMD", "uv run python agent.py --submit --json"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path(".env")) if Path(".env").exists() else None
    args = parse_args(argv)
    Path(args.log_dir).mkdir(parents=True, exist_ok=True)

    client = HarnessServiceClientSync(args.host)
    print("Connecting to BitGN:", retry_call(lambda: client.status(StatusRequest())).status)
    benchmark = retry_call(lambda: client.get_benchmark(GetBenchmarkRequest(benchmark_id=args.benchmark_id)))
    print(
        f"{EvalPolicy.Name(benchmark.policy)} {benchmark.benchmark_id}: {len(benchmark.tasks)} tasks "
        f"| model {args.model} | parallel {args.parallel} | logs {args.log_dir}"
    )

    task_filter = set(args.tasks)
    results: list[TaskResult] = []
    wall_start = time.time()
    samples_path = Path(args.log_dir) / "samples.jsonl"
    if samples_path.exists():
        samples_path.unlink()
    for sample_index in range(1, args.repeat + 1):
        run = client.start_run(
            StartRunRequest(
                name="@ai_nuts_and_bolts_autoresearch",
                benchmark_id=args.benchmark_id,
                api_key=args.api_key,
            )
        )
        try:
            with ThreadPoolExecutor(max_workers=args.parallel) as pool:
                futures = [
                    pool.submit(run_one, trial_id, task_filter, args, sample_index)
                    for trial_id in run.trial_ids
                ]
                for future in as_completed(futures):
                    result = future.result()
                    if result.error == "skip":
                        continue
                    results.append(result)
                    write_sample_record(samples_path, result)
                    tag = f"{result.score:.2f}" if isinstance(result.score, (float, int)) else (result.error or "n/a")
                    repeat_tag = f" r{sample_index:02d}" if args.repeat > 1 else ""
                    print(f"[done]{repeat_tag} {result.task_id}: {tag} ({result.seconds:.0f}s)", flush=True)
        finally:
            client.submit_run(SubmitRunRequest(run_id=run.run_id, force=True))
    wall = time.time() - wall_start

    print("\n==== SUMMARY ====")
    scored = []
    times = []
    for result in sorted(results, key=lambda item: item.task_id):
        times.append(result.seconds)
        if isinstance(result.score, (float, int)):
            scored.append(result.score)
            line = f"{result.task_id}: {result.score:.2f} ({result.seconds:.0f}s)"
            if result.score < 1.0 and result.detail:
                line += "  | " + " ; ".join(result.detail)[:240]
        else:
            line = f"{result.task_id}: ERROR {result.error}"
        print(line)

    if scored:
        perfect = sum(1 for score in scored if score >= 0.999)
        pct = sum(scored) / len(scored) * 100
        avg = sum(times) / len(times) if times else 0.0
        slowest = max(times) if times else 0.0
        print(
            f"\nFINAL: {pct:.2f}%  ({perfect}/{len(scored)} perfect, {len(scored)} scored)\n"
            f"SPEED: wall {wall:.0f}s | avg/task {avg:.0f}s | slowest {slowest:.0f}s | parallel {args.parallel}"
        )
    print(f"per-task logs: {args.log_dir}/<task>.log or <task>-rNN.log")
    print(f"samples: {samples_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
