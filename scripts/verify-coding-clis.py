"""Credential-free image smoke checks and installed coding CLI inventory."""

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


TOOLS = ("claude", "codex", "copilot", "grok", "kiro-cli", "cursor-agent")
# Sonnet 5.5 requires this CLI release; older aliases select older models.
MIN_CLAUDE_VERSION = (2, 1, 284)


def validate_version(tool, output):
    output = output.strip()
    if not output:
        raise ValueError(f"{tool} returned no version")
    if tool == "claude":
        match = re.search(r"\b(\d+)\.(\d+)\.(\d+)(?![\w.-])", output)
        if not match or tuple(map(int, match.groups())) < MIN_CLAUDE_VERSION:
            raise ValueError(f"Claude Code >= 2.1.284 is required; found {output!r}")
    return output


def inventory():
    if Path("/usr/local/bin/agent").resolve() != Path("/usr/local/bin/grok-build-cli"):
        raise ValueError("The global agent alias must still belong to Grok Build")
    versions = {}
    with tempfile.TemporaryDirectory(prefix="coding-cli-smoke-") as home:
        # Isolated HOME prevents smoke tests from relying on a signed-in account.
        env = dict(os.environ, HOME=home, CI="1", NO_COLOR="1")
        for tool in TOOLS:
            result = subprocess.run(
                [tool, "--version"],
                env=env,
                cwd=home,
                capture_output=True,
                text=True,
                timeout=45,
                check=True,
            )
            versions[tool] = validate_version(tool, result.stdout or result.stderr)
    return versions


if __name__ == "__main__":
    print(json.dumps(inventory(), indent=2, sort_keys=True))
