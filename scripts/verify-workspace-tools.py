"""Credential-free, non-root workspace tool probes using disposable fixtures."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile


ESLINT_CONFIG = "/usr/local/share/safeexecute/eslint.config.cjs"


def probe_environment(home):
    # Do not forward provider credentials, Python/Node hooks or user npm config.
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(home),
        "TMPDIR": str(home),
        "XDG_CACHE_HOME": str(home / "cache"),
        "LANG": "C.UTF-8",
        "CI": "1",
        "NO_COLOR": "1",
        "npm_config_cache": str(home / "npm-cache"),
        "npm_config_userconfig": "/dev/null",
        "npm_config_offline": "true",
        "npm_config_ignore_scripts": "true",
    }


def inventory():
    if os.geteuid() == 0:
        raise RuntimeError("Workspace probes must run as a non-root user")
    with tempfile.TemporaryDirectory(prefix="workspace-tools-smoke-") as directory:
        root = Path(directory)
        env = probe_environment(root)

        def run(*args, input=None, expected=0):
            result = subprocess.run(
                args,
                cwd=root,
                env=env,
                input=input,
                capture_output=True,
                text=True,
                timeout=90,
            )
            if result.returncode != expected:
                raise RuntimeError(
                    f"{args[0]} exited {result.returncode}, expected {expected}: "
                    f"{result.stdout}\n{result.stderr}"
                )
            return result.stdout

        versions = {}
        for name, command in {
            "pandoc": ("pandoc", "--version"),
            "pdflatex": ("pdflatex", "--version"),
            "black": ("python3", "-I", "-m", "black", "--version"),
            "pylint": ("python3", "-I", "-m", "pylint", "--version"),
            "eslint": ("npx", "--no-install", "eslint", "--version"),
            "prettier": ("npx", "--no-install", "prettier", "--version"),
            "ffmpeg": ("ffmpeg", "-version"),
            "ffprobe": ("ffprobe", "-version"),
        }.items():
            versions[name] = run(*command).splitlines()[0]

        markdown = "# Sandbox document\n\nA **local** conversion.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"
        run("pandoc", "--from=markdown", "-o", "probe.pdf", input=markdown)
        if not (root / "probe.pdf").read_bytes().startswith(b"%PDF-"):
            raise RuntimeError("Pandoc did not produce a PDF")
        run("pandoc", "--from=markdown", "-o", "probe.docx", input=markdown)
        with zipfile.ZipFile(root / "probe.docx") as document:
            if b"Sandbox document" not in document.read("word/document.xml"):
                raise RuntimeError("Pandoc DOCX content missing")

        (root / "probe.py").write_text('"""Probe."""\nVALUE=42\n')
        run("python3", "-I", "-m", "black", "--config", "/dev/null", "--", "probe.py")
        run(
            "python3",
            "-I",
            "-m",
            "black",
            "--config",
            "/dev/null",
            "--check",
            "--",
            "probe.py",
        )
        pylint = (
            "python3",
            "-I",
            "-m",
            "pylint",
            "--rcfile=/dev/null",
            "--output-format=json",
        )
        if json.loads(run(*pylint, "--", "probe.py")):
            raise RuntimeError("Valid Python failed lint")
        (root / "bad.py").write_text('"""Probe."""\nprint(missing_name)\n')
        messages = json.loads(
            run(*pylint, "--disable=all", "--enable=E0602", "--", "bad.py", expected=2)
        )
        if not any(message["message-id"] == "E0602" for message in messages):
            raise RuntimeError("Pylint did not diagnose undefined name")

        eslint = (
            "npx",
            "--no-install",
            "eslint",
            "--no-config-lookup",
            "--config",
            ESLINT_CONFIG,
            "--no-inline-config",
            "--format=json",
        )
        for extension, source in (
            ("js", "export const value=42"),
            ("ts", "export const value:number=42"),
            ("json", '{"value":42}'),
        ):
            filename = f"probe.{extension}"
            (root / filename).write_text(source)
            run(
                "npx",
                "--no-install",
                "prettier",
                "--no-config",
                "--write",
                "--",
                filename,
            )
            run(
                "npx",
                "--no-install",
                "prettier",
                "--no-config",
                "--check",
                "--",
                filename,
            )
            if extension != "json":
                messages = json.loads(run(*eslint, "--", filename))
                if (
                    len(messages) != 1
                    or messages[0]["errorCount"]
                    or messages[0]["warningCount"]
                ):
                    raise RuntimeError(f"ESLint did not lint {extension} cleanly")
        (root / "bad.js").write_text("debugger;\n")
        messages = json.loads(run(*eslint, "--", "bad.js", expected=1))
        if not any(
            message["ruleId"] == "no-debugger" for message in messages[0]["messages"]
        ):
            raise RuntimeError("ESLint did not diagnose debugger statement")

        # Real spreadsheet, image and PDF reads, not just import/version checks.
        run(
            "python3",
            "-I",
            "-c",
            """
import pandas as pd
from PIL import Image
import fitz
frame = pd.DataFrame({'value': [42]})
frame.to_excel('probe.xlsx', index=False)
assert pd.read_excel('probe.xlsx').iloc[0, 0] == 42
Image.new('RGB', (16, 16), 'red').save('probe.png')
assert Image.open('probe.png').size == (16, 16)
with fitz.open('probe.pdf') as document:
    assert 'Sandbox document' in document[0].get_text()
""",
        )
        (root / "captions.srt").write_text("1\n00:00:00,000 --> 00:00:00,300\nProbe\n")
        run(
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-threads",
            "1",
            "-filter_threads",
            "1",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=64x64:r=10:d=0.3",
            "-vf",
            "subtitles=captions.srt",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-pix_fmt",
            "yuv420p",
            "-y",
            "probe.mp4",
        )
        video = json.loads(
            run("ffprobe", "-v", "error", "-show_streams", "-of", "json", "probe.mp4")
        )
        if (
            video["streams"][0]["codec_name"] != "h264"
            or video["streams"][0]["width"] != 64
        ):
            raise RuntimeError("FFmpeg subtitle render failed")
        return versions


if __name__ == "__main__":
    print(json.dumps(inventory(), indent=2, sort_keys=True))
