import argparse
import json
import tempfile
import unittest
from pathlib import Path

from evaluator import TaskResult, instruction_hash, parse_args, sample_log_path, write_sample_record


class EvaluatorTests(unittest.TestCase):
    def test_sample_log_path_keeps_repeated_runs_distinct(self):
        root = Path("runs/sample")

        self.assertEqual(sample_log_path(root, "t15", 1, 1), root / "t15.log")
        self.assertEqual(sample_log_path(root, "t15", 1, 3), root / "t15-r01.log")
        self.assertEqual(sample_log_path(root, "t15", 3, 3), root / "t15-r03.log")

    def test_instruction_hash_is_stable(self):
        self.assertEqual(instruction_hash(" count widgets "), instruction_hash(" count widgets "))
        self.assertNotEqual(instruction_hash("count widgets"), instruction_hash("count paint"))

    def test_write_sample_record_appends_jsonl(self):
        result = TaskResult(
            task_id="t49",
            score=0.0,
            detail=["answer contains too many invalid references"],
            error=None,
            seconds=1.25,
            sample_index=2,
            instruction_hash="abc123",
            instruction="How many Wall Paint?",
            log_path="runs/sample/t49-r02.log",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "samples.jsonl"

            write_sample_record(path, result)

            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            payload = json.loads(lines[0])
            self.assertEqual(payload["task_id"], "t49")
            self.assertEqual(payload["sample_index"], 2)
            self.assertEqual(payload["instruction_hash"], "abc123")
            self.assertEqual(payload["score"], 0.0)

    def test_default_agent_command_uses_uv_environment(self):
        args = parse_args([])

        self.assertEqual(args.agent_cmd, "uv run python agent.py --submit --json")


if __name__ == "__main__":
    unittest.main()
