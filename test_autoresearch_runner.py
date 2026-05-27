import tempfile
import unittest
from pathlib import Path

from autoresearch_runner import (
    EDITABLE_EXPERIMENT_FILES,
    Experiment,
    Score,
    append_result_row,
    build_codex_command,
    build_eval_command,
    copy_workspace,
    parse_sweep_summary,
    record_candidate_decision,
    should_keep_candidate,
    task_ids_hash,
    write_experiment_files,
)


class AutoresearchRunnerTests(unittest.TestCase):
    def test_editable_surface_is_independent_agent_only(self):
        self.assertEqual(EDITABLE_EXPERIMENT_FILES, ("agent.py",))

    def test_build_codex_command_uses_requested_model_and_readonly_sandbox(self):
        command = build_codex_command(
            model="gpt-5.3-codex",
            repo=Path("/tmp/target"),
            prompt="hello",
            output=Path("/tmp/out.txt"),
        )

        self.assertEqual(command[:3], ["codex", "exec", "-m"])
        self.assertIn("gpt-5.3-codex", command)
        self.assertIn("--sandbox", command)
        self.assertIn("read-only", command)
        self.assertIn("-C", command)
        self.assertIn(str(Path("/tmp/target").resolve()), command)
        self.assertIn("--output-last-message", command)

    def test_build_eval_command_targets_fixed_evaluator(self):
        command = build_eval_command(
            tasks=["t15", "t49"],
            model="codex:gpt-5.3-codex",
            parallel=4,
            log_dir=Path("runs/example"),
        )

        self.assertEqual(command[:2], ["python3", "evaluator.py"])
        self.assertIn("--model", command)
        self.assertIn("codex:gpt-5.3-codex", command)
        self.assertIn("--parallel", command)
        self.assertIn("4", command)
        self.assertEqual(command[-2:], ["t15", "t49"])

    def test_write_experiment_files_creates_prompt_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            exp = Experiment(
                name="trial",
                model="gpt-5.3-codex",
                target_repo=Path("/repo"),
                task="Study the repo.",
                out_dir=Path(tmp),
            )

            write_experiment_files(exp)

            self.assertTrue((Path(tmp) / "prompt.md").exists())
            metadata = (Path(tmp) / "metadata.json").read_text(encoding="utf-8")
            self.assertIn("gpt-5.3-codex", metadata)
            self.assertIn("/repo", metadata)

    def test_parse_sweep_summary_extracts_score_speed_and_failed_tasks(self):
        log = """
==== SUMMARY ====
t05: 0.00 (33s)  | Answer should contain '<NO>'
t16: 0.00 (1s)  | answer missing required reference '/proc/catalog/x.json'
t26: 1.00 (1s)
t48: 0.00 (1s)  | expected outcome OUTCOME_DENIED_SECURITY, got OUTCOME_OK

FINAL: 91.67%  (44/48 perfect, 48 scored)
SPEED: wall 361s | avg/task 30s | slowest 175s | parallel 6
"""

        score = parse_sweep_summary(log)

        self.assertEqual(score.perfect, 44)
        self.assertEqual(score.total, 48)
        self.assertEqual(score.wall_seconds, 361)
        self.assertTrue(score.security_regression)
        self.assertEqual(score.failed_tasks, ["t05", "t16", "t48"])
        self.assertEqual(score.task_ids, ("t05", "t16", "t26", "t48"))

    def test_task_ids_hash_is_stable_and_order_insensitive(self):
        self.assertEqual(task_ids_hash(["t02", "t01"]), task_ids_hash(["t01", "t02"]))
        self.assertNotEqual(task_ids_hash(["t01", "t02"]), task_ids_hash(["t01", "t03"]))

    def test_should_keep_candidate_prioritizes_perfect_count_then_speed(self):
        baseline = Score(
            perfect=44,
            total=48,
            wall_seconds=361,
            failed_tasks=[],
            security_regression=False,
            task_ids=tuple(f"t{i:02d}" for i in range(1, 49)),
        )

        self.assertTrue(
            should_keep_candidate(
                baseline,
                Score(
                    perfect=45,
                    total=48,
                    wall_seconds=900,
                    failed_tasks=[],
                    security_regression=False,
                    task_ids=baseline.task_ids,
                ),
            )
        )
        self.assertFalse(
            should_keep_candidate(
                baseline,
                Score(
                    perfect=46,
                    total=48,
                    wall_seconds=200,
                    failed_tasks=[],
                    security_regression=True,
                    task_ids=baseline.task_ids,
                ),
            )
        )
        self.assertTrue(
            should_keep_candidate(
                Score(
                    perfect=3,
                    total=3,
                    wall_seconds=400,
                    failed_tasks=[],
                    security_regression=False,
                    task_ids=("t01", "t02", "t03"),
                ),
                Score(
                    perfect=3,
                    total=3,
                    wall_seconds=250,
                    failed_tasks=[],
                    security_regression=False,
                    task_ids=("t01", "t02", "t03"),
                ),
            )
        )

    def test_should_not_keep_candidate_against_different_task_set(self):
        baseline = Score(
            perfect=2,
            total=2,
            wall_seconds=300,
            failed_tasks=[],
            security_regression=False,
            task_ids=("t01", "t02"),
        )
        candidate = Score(
            perfect=3,
            total=3,
            wall_seconds=310,
            failed_tasks=[],
            security_regression=False,
            task_ids=("t01", "t02", "t03"),
        )

        self.assertFalse(should_keep_candidate(baseline, candidate))

    def test_append_result_row_writes_tsv_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.tsv"
            score = Score(
                perfect=45,
                total=49,
                wall_seconds=250,
                failed_tasks=["t16"],
                security_regression=False,
                task_ids=("t01", "t16"),
            )

            append_result_row(path, commit="abc1234", score=score, status="keep", description="t16 branch")

            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(
                lines[0],
                "commit\tperfect\ttotal\ttask_ids_hash\twall_seconds\tstatus\tfailed_tasks\tdescription",
            )
            self.assertEqual(
                lines[1],
                f"abc1234\t45\t49\t{task_ids_hash(('t01', 't16'))}\t250\tkeep\tt16\tt16 branch",
            )

    def test_record_candidate_decision_compares_logs_and_writes_keep_status(self):
        baseline_log = """
t16: 0.00 (1s)
FINAL: 44.00%  (44/49 perfect, 49 scored)
SPEED: wall 361s | avg/task 30s | slowest 175s | parallel 6
"""
        candidate_log = """
t16: 1.00 (1s)
FINAL: 45.00%  (45/49 perfect, 49 scored)
SPEED: wall 400s | avg/task 31s | slowest 190s | parallel 6
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline_path = root / "baseline.log"
            candidate_path = root / "candidate.log"
            ledger_path = root / "results.tsv"
            baseline_path.write_text(baseline_log, encoding="utf-8")
            candidate_path.write_text(candidate_log, encoding="utf-8")

            status = record_candidate_decision(
                baseline_path,
                candidate_path,
                ledger_path,
                commit="def5678",
                description="close t16",
            )

            self.assertEqual(status, "keep")
            self.assertIn(
                "def5678\t45\t49\t",
                ledger_path.read_text(encoding="utf-8"),
            )
            self.assertIn("\t400\tkeep\t\tclose t16", ledger_path.read_text(encoding="utf-8"))

    def test_record_candidate_decision_requires_new_baseline_for_changed_task_set(self):
        baseline_log = """
t01: 1.00 (1s)
FINAL: 100.00%  (1/1 perfect, 1 scored)
SPEED: wall 1s | avg/task 1s | slowest 1s | parallel 1
"""
        candidate_log = """
t01: 1.00 (1s)
t02: 1.00 (1s)
FINAL: 100.00%  (2/2 perfect, 2 scored)
SPEED: wall 2s | avg/task 1s | slowest 1s | parallel 1
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline_path = root / "baseline.log"
            candidate_path = root / "candidate.log"
            ledger_path = root / "results.tsv"
            baseline_path.write_text(baseline_log, encoding="utf-8")
            candidate_path.write_text(candidate_log, encoding="utf-8")

            status = record_candidate_decision(
                baseline_path,
                candidate_path,
                ledger_path,
                commit="newbench",
                description="current prod task count changed",
            )

            self.assertEqual(status, "new_baseline_required")
            self.assertIn("\tnew_baseline_required\t", ledger_path.read_text(encoding="utf-8"))

    def test_copy_workspace_excludes_local_experiment_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            workspace = root / "workspace"
            source.mkdir()
            (source / "agent.py").write_text("# agent\n", encoding="utf-8")
            (source / "results.tsv").write_text("commit\tperfect\n", encoding="utf-8")
            for name in ["runs", "experiments", "worktrees", ".worktrees"]:
                artifact_dir = source / name
                artifact_dir.mkdir()
                (artifact_dir / "artifact.txt").write_text("x\n", encoding="utf-8")

            copy_workspace(source, workspace)

            self.assertTrue((workspace / "agent.py").exists())
            self.assertFalse((workspace / "results.tsv").exists())
            for name in ["runs", "experiments", "worktrees", ".worktrees"]:
                self.assertFalse((workspace / name).exists())


if __name__ == "__main__":
    unittest.main()
