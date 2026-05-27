import tempfile
import unittest
from pathlib import Path

from autoresearch_runner import Experiment, build_codex_command, write_experiment_files


class AutoresearchRunnerTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
