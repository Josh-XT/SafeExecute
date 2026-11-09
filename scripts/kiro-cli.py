#!/usr/bin/python3 -I
"""Install optional Kiro tooling inside the caller's sandbox on first use."""

import fcntl
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


INSTALL_URL = "https://cli.kiro.dev/install"
INSTALL_TIMEOUT = 600


def ensure_installed(home):
    if not home.is_absolute():
        raise ValueError("Kiro requires an absolute, scoped HOME")
    root = home / ".local/share/safeexecute/kiro"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    binary = root / ".local/bin/kiro-cli"
    ready = root / "installed"
    # Release the installation lock before running an arbitrarily long chat.
    with (root / "install.lock").open("a") as lock:
        deadline = time.monotonic() + INSTALL_TIMEOUT
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Timed out waiting for Kiro installation")
                time.sleep(0.1)
        if ready.is_file() and os.access(binary, os.X_OK):
            return binary
        ready.unlink(missing_ok=True)
        # Keep downloaded installers away from provider tokens and shell hooks.
        env = {"HOME": str(root), "PATH": "/usr/local/bin:/usr/bin:/bin"}
        with tempfile.TemporaryDirectory(prefix="download-", dir=root) as tmp:
            installer = Path(tmp) / "install.sh"
            subprocess.run(
                [
                    "curl",
                    "--proto",
                    "=https",
                    "--proto-redir",
                    "=https",
                    "--tlsv1.2",
                    "-fsSL",
                    "--connect-timeout",
                    "20",
                    "--max-time",
                    "120",
                    INSTALL_URL,
                    "-o",
                    str(installer),
                ],
                env=env,
                cwd=tmp,
                check=True,
                timeout=130,
                stdout=sys.stderr,
            )
            subprocess.run(
                ["bash", str(installer), "--force", "--no-modify-path"],
                env=env,
                cwd=tmp,
                check=True,
                timeout=INSTALL_TIMEOUT,
                stdin=subprocess.DEVNULL,
                stdout=sys.stderr,
            )
        subprocess.run(
            [str(binary), "--version"],
            env=env,
            cwd=root,
            check=True,
            timeout=45,
            stdin=subprocess.DEVNULL,
            stdout=sys.stderr,
        )
        ready.touch(mode=0o600)
    return binary


def main():
    try:
        binary = ensure_installed(Path(os.environ["HOME"]))
        os.execv(str(binary), [str(binary), *sys.argv[1:]])
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f"Kiro startup failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
