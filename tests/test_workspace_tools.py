import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "verify_workspace_tools", ROOT / "scripts/verify-workspace-tools.py"
)
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class WorkspaceToolsTest(unittest.TestCase):
    @patch.object(verify.os, "geteuid", return_value=0)
    def test_root_probes_are_rejected(self, geteuid):
        with self.assertRaisesRegex(RuntimeError, "non-root"):
            verify.inventory()

    def test_environment_does_not_forward_credentials_or_runtime_hooks(self):
        with patch.dict(
            os.environ,
            {
                "EXAMPLE_API_KEY": "fixture",
                "NODE_OPTIONS": "fixture",
                "PYTHONPATH": "fixture",
            },
        ):
            env = verify.probe_environment(Path("/tmp/fixture"))
        for key in ("EXAMPLE_API_KEY", "NODE_OPTIONS", "PYTHONPATH"):
            self.assertNotIn(key, env)
        self.assertEqual(env["HOME"], "/tmp/fixture")
        self.assertEqual(env["npm_config_offline"], "true")
        self.assertEqual(env["npm_config_userconfig"], "/dev/null")

    @patch.object(verify.os, "geteuid", return_value=1000)
    @patch.object(verify.subprocess, "run", side_effect=FileNotFoundError("pandoc"))
    def test_missing_tools_fail_the_probe(self, run, geteuid):
        with self.assertRaises(FileNotFoundError):
            verify.inventory()
        self.assertEqual(run.call_args.args[0], ("pandoc", "--version"))
        self.assertEqual(run.call_args.kwargs["timeout"], 90)
        self.assertNotIn("shell", run.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
