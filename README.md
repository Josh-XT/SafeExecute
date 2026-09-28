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
GitHub Copilot, Cursor, Grok Build, and Kiro from their official latest installers.
CI changes `CODING_CLI_REFRESH` on each build so Docker cannot reuse stale CLI
installation layers. The scientific tools, browser, and TypeScript layers remain
cacheable. For a local refresh without discarding the entire build cache:

```bash
docker build --pull --build-arg CODING_CLI_REFRESH="$(date -u +%Y%m%d%H%M%S)" -t joshxt/safeexecute:latest .
```

All six executables must pass a version probe as the unprivileged workspace
user before an image is published. Claude must be at least 2.1.284 for the
[Opus/Sonnet 5.5 aliases](https://code.claude.com/docs/en/model-config).
Installed versions are recorded at
`/usr/local/share/safeexecute/coding-cli-versions.json`. These are credential-free
startup checks, not end-to-end provider authentication or inference tests.

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
