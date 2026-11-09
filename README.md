# SafeExecute

[![GitHub](https://img.shields.io/badge/GitHub-Sponsor%20Josh%20XT-blue?logo=github&style=plastic)](https://github.com/sponsors/Josh-XT) [![PayPal](https://img.shields.io/badge/PayPal-Sponsor%20Josh%20XT-blue.svg?logo=paypal&style=plastic)](https://paypal.me/joshxt) [![Ko-Fi](https://img.shields.io/badge/Kofi-Sponsor%20Josh%20XT-blue.svg?logo=kofi&style=plastic)](https://ko-fi.com/joshxt)

This module provides a safe way to execute Python code in a container. It is intended to be used with language models to enable them to execute code in a safe environment separate from the host machine (your computer or server).

The container comes preloaded with the following packages:

- numpy
- matplotlib
- seaborn
- scikit-learn
- yfinance
- scipy
- statsmodels
- sympy
- bokeh
- plotly
- dash
- networkx
- pyvis
- pandas
- agixtsdk

## Coding Tools

The image includes Node/npm and the official TypeScript compiler (`tsc`). The
fallback version is pinned by the Docker build argument `TYPESCRIPT_VERSION`.
For a repository, install its locked development dependencies and use its own
typecheck script so its compiler version takes precedence. The compiler package
is `typescript`, not the unrelated npm package named `tsc`.

Cursor CLI is installed as `/usr/local/bin/cursor-agent`. The global `agent`
alias still belongs to Grok Build. WorkConductor uses a private scoped HOME for
Cursor credentials and sessions; no account is logged in during image building.
Older images remain compatible with WorkConductor's on-demand Cursor installer.

Image builds run `tests/typescript-smoke.mjs` to verify real compilation,
type-error failures, project-local tool precedence and exit-code preservation.
They also check Cursor's version and ensure Grok's alias is unchanged. Verify
provider login separately with an authorized account after deployment.

### Keeping Coding CLIs Current

Daily image publication and every manual/push build refresh Claude Code, Codex,
GitHub Copilot, Cursor, and Grok Build from their official latest installers.
CI changes `CODING_CLI_REFRESH` on each build so Docker cannot reuse stale CLI
installation layers. The scientific tools, browser, and TypeScript layers remain
cacheable. For a local refresh without discarding the entire build cache:

```bash
docker build --pull --build-arg CODING_CLI_REFRESH="$(date -u +%Y%m%d%H%M%S)" -t joshxt/safeexecute:latest .
```

All five bundled executables must pass a version probe as the unprivileged workspace
user before an image is published. Claude must be at least 2.1.284 for the
[Opus/Sonnet 5.5 aliases](https://code.claude.com/docs/en/model-config).
Installed versions are recorded at
`/usr/local/share/safeexecute/coding-cli-versions.json`. These are credential-free
startup checks, not end-to-end provider authentication or inference tests.

Kiro is optional. The `kiro-cli` launcher downloads it on first invocation inside
the user's sandbox using the [official installer](https://cli.kiro.dev/install).
No Kiro download or installation runs during image builds or their version probes.
The installation is cached under the scoped HOME, uses no sudo, and is serialized
for concurrent callers. Installer processes receive no provider credentials;
the CLI itself retains the caller's environment and HOME for authentication.
First use requires outbound access to Kiro's download services. A failed install
fails that invocation and can be retried without affecting other workspace tools.

On deployed hosts, pull the new image and retire old sandbox containers only
after their work and CLI sign-in sessions finish. Pulling an image does **not**
update existing containers; WorkConductor also reuses a locally cached image.
Preserve workspace mounts and credentials when replacing a container. We do not
upgrade running CLI processes or destroy active workspaces as part of publication.

```bash
docker pull joshxt/safeexecute:latest
docker run --rm --user safeexecute --entrypoint python3 joshxt/safeexecute:latest /usr/local/bin/verify-coding-clis.py
```

References: [TypeScript installation](https://www.typescriptlang.org/download/)
and [Cursor CLI installation](https://cursor.com/docs/cli/installation).

## Workspace Document and Media Tools

A late image layer adds Pandoc, Black, Pylint, ESLint, Prettier and the
TypeScript ESLint parser without rebuilding the scientific/browser layers.
Pandoc uses the existing `pdflatex` engine, with Latin Modern fonts for its
default template. FFmpeg/FFprobe, pandas, openpyxl, Pillow and PyMuPDF remain
provided by the earlier layers. No runtime package download or account login
is needed for these tools.

Python tools support isolated invocations such as `python3 -I -m black` and
`python3 -I -m pylint`. ESLint and Prettier are globally installed and available
through `npx --no-install`. Version pins are Docker build arguments:
`BLACK_VERSION`, `PYLINT_VERSION`, `ESLINT_VERSION`, `PRETTIER_VERSION`, and
`TYPESCRIPT_ESLINT_PARSER_VERSION`.

For standalone JavaScript/TypeScript files, the image provides a fixed config
with syntax checking and basic debugger/unreachable-code rules:

```bash
npx --no-install eslint --no-config-lookup --config /usr/local/share/safeexecute/eslint.config.cjs --no-inline-config --format=json -- example.ts
npx --no-install prettier --no-config --write -- example.ts
```

This config is not project-specific or type-aware linting. Projects requiring
their own rules/plugins should install their locked dependencies and run their
lint script inside the sandbox. Document engines, project code and lint plugins
must execute inside the sandbox, not on the host.

The image build runs `verify-workspace-tools.py` as the non-root workspace user.
It creates disposable PDF/DOCX/XLSX/PNG files, checks PDF text and spreadsheet
contents, formats Python/JS/TS/JSON, checks both passing and failing lint results,
and renders a short H.264 video with subtitles. Its subprocess environment is
allowlisted, its HOME/cache directories are temporary, and npm is offline.
Installed versions are recorded in
`/usr/local/share/safeexecute/workspace-tool-versions.json`.

Repeat the probes without network access, credentials or host mounts:

```bash
docker run --rm --network none --user 1000:1000 --cap-drop ALL --security-opt no-new-privileges --read-only --tmpfs /tmp:rw,nosuid,nodev,size=256m --pids-limit 128 --memory 1g --cpus 2 --entrypoint python3 joshxt/safeexecute:latest -I /usr/local/bin/verify-workspace-tools.py
```

These are local tool-readiness checks, not verification of every sandbox policy
or every project configuration. Testing a derived image on an existing cached
base does not verify a complete fresh image build or another architecture.

## Installation

```bash
pip install safeexecute
```

## Usage

You can pass an entire message from a langauge model into the `code` field and it will parse out any Python code blocks and execute them.  If anywhere in the `code` says `pip install <package>`, it will install the package in the container before executing the code.

```python
from safeexecute import execute_python_code

code = "print('Hello, World!')"
result = execute_python_code(code=code)
print(result)
```
