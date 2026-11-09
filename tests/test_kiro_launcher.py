import importlib.util
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("kiro", ROOT / "scripts/kiro-cli.py")
kiro = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kiro)


class KiroLauncherTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.binary = self.home / ".local/share/safeexecute/kiro/.local/bin/kiro-cli"

    def install(self, args, **kwargs):
        if args[0] == "bash":
            self.binary.parent.mkdir(parents=True, exist_ok=True)
            self.binary.write_text("#!/bin/sh\nexit 0\n")
            self.binary.chmod(0o700)
        return subprocess.CompletedProcess(args, 0)

    def test_first_use_installs_without_secrets_then_reuses_cache(self):
        with patch.dict(os.environ, {"KIRO_API_KEY": "private-test-token"}):
            with patch.object(kiro.subprocess, "run", side_effect=self.install) as run:
                self.assertEqual(kiro.ensure_installed(self.home), self.binary)
                self.assertEqual(run.call_count, 3)
                for call in run.call_args_list:
                    self.assertEqual(set(call.kwargs["env"]), {"HOME", "PATH"})
                    self.assertTrue(call.kwargs["check"])
                    self.assertGreater(call.kwargs["timeout"], 0)
                self.assertIn(kiro.INSTALL_URL, run.call_args_list[0].args[0])
                self.assertEqual(
                    run.call_args_list[1].args[0][-2:],
                    ["--force", "--no-modify-path"],
                )
                run.reset_mock()
                self.assertEqual(kiro.ensure_installed(self.home), self.binary)
                run.assert_not_called()

    def test_failed_install_does_not_mark_ready_and_can_retry(self):
        for failure in (
            subprocess.CalledProcessError(1, "bash"),
            subprocess.TimeoutExpired("bash", 600),
        ):
            with patch.object(kiro.subprocess, "run", side_effect=failure):
                with self.assertRaises(type(failure)):
                    kiro.ensure_installed(self.home)
            self.assertFalse((self.binary.parents[2] / "installed").exists())
        with patch.object(kiro.subprocess, "run", side_effect=self.install):
            self.assertEqual(kiro.ensure_installed(self.home), self.binary)

    def test_concurrent_callers_share_one_install(self):
        def slow_install(args, **kwargs):
            if args[0] == "bash":
                time.sleep(0.1)
            return self.install(args, **kwargs)

        with patch.object(kiro.subprocess, "run", side_effect=slow_install) as run:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(kiro.ensure_installed, [self.home, self.home]))
            self.assertEqual(results, [self.binary, self.binary])
            self.assertEqual(run.call_count, 3)

    def test_failed_version_probe_is_not_cached(self):
        def broken(args, **kwargs):
            if args[-1] == "--version":
                raise subprocess.CalledProcessError(127, args)
            return self.install(args, **kwargs)

        with patch.object(kiro.subprocess, "run", side_effect=broken):
            with self.assertRaises(subprocess.CalledProcessError):
                kiro.ensure_installed(self.home)
        self.assertFalse((self.binary.parents[2] / "installed").exists())

    def test_relative_home_rejected_before_install(self):
        with patch.object(kiro.subprocess, "run") as run:
            with self.assertRaises(ValueError):
                kiro.ensure_installed(Path("relative"))
            run.assert_not_called()

    def test_dispatch_preserves_arguments_and_authentication_home(self):
        env = {"HOME": str(self.home), "KIRO_API_KEY": "private-test-token"}
        with patch.dict(os.environ, env):
            with patch.object(kiro, "ensure_installed", return_value=self.binary):
                with patch.object(kiro.os, "execv") as execute:
                    with patch.object(kiro.sys, "argv", ["kiro-cli", "chat", "a b"]):
                        kiro.main()
                    execute.assert_called_once_with(
                        str(self.binary), [str(self.binary), "chat", "a b"]
                    )
                    self.assertEqual(os.environ["HOME"], str(self.home))
                    self.assertEqual(os.environ["KIRO_API_KEY"], env["KIRO_API_KEY"])

    def test_image_only_copies_launcher(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        self.assertIn("COPY --chmod=0755 scripts/kiro-cli.py", dockerfile)
        self.assertNotIn("kirocli/install.sh", dockerfile)
        self.assertNotIn("kiro-cli --version", dockerfile)


if __name__ == "__main__":
    unittest.main()
