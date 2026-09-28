import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "verify_coding_clis", ROOT / "scripts/verify-coding-clis.py"
)
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class CodingCliVersionsTest(unittest.TestCase):
    def test_claude_requires_version_with_current_model_aliases(self):
        for version in ("2.1.270 (Claude Code)", "2.1.283", "unknown", "2.1.284-beta"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                verify.validate_version("claude", version)
        for version in ("2.1.284 (Claude Code)", "2.1.300", "2.2.0", "3.0.0"):
            self.assertEqual(verify.validate_version("claude", version), version)

    def test_cursor_date_versions_and_empty_output(self):
        self.assertEqual(
            verify.validate_version("cursor-agent", "2026.09.28-abc\n"),
            "2026.09.28-abc",
        )
        with self.assertRaises(ValueError):
            verify.validate_version("codex", " \n")

    @patch.object(
        verify.Path, "resolve", return_value=Path("/usr/local/bin/grok-build-cli")
    )
    @patch.object(verify.subprocess, "run")
    def test_all_six_tools_probed_without_inference(self, run, resolve):
        run.return_value = subprocess.CompletedProcess([], 0, "2.1.284", "")
        self.assertEqual(set(verify.inventory()), set(verify.TOOLS))
        self.assertEqual(run.call_count, 6)
        for call in run.call_args_list:
            self.assertEqual(call.args[0][1:], ["--version"])
            self.assertEqual(call.kwargs["timeout"], 45)
            self.assertTrue(call.kwargs["check"])
            self.assertIn("coding-cli-smoke-", call.kwargs["env"]["HOME"])

    @patch.object(
        verify.Path, "resolve", return_value=Path("/usr/local/bin/grok-build-cli")
    )
    @patch.object(verify.subprocess, "run")
    def test_failed_or_hung_tool_fails_build(self, run, resolve):
        for error in (
            subprocess.CalledProcessError(1, "claude"),
            subprocess.TimeoutExpired("claude", 45),
            FileNotFoundError("claude"),
        ):
            run.side_effect = error
            with self.assertRaises(type(error)):
                verify.inventory()

    @patch.object(verify.Path, "resolve", return_value=Path("/opt/cursor-cli/agent"))
    def test_cursor_cannot_replace_grok_alias(self, resolve):
        with self.assertRaisesRegex(ValueError, "Grok"):
            verify.inventory()


if __name__ == "__main__":
    unittest.main()
