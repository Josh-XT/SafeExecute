# SafeExecute

[![GitHub](https://img.shields.io/badge/GitHub-Sponsor%20Josh%20XT-blue?logo=github&style=plastic)](https://github.com/sponsors/Josh-XT) [![PayPal](https://img.shields.io/badge/PayPal-Sponsor%20Josh%20XT-blue.svg?logo=paypal&style=plastic)](https://paypal.me/joshxt) [![Ko-Fi](https://img.shields.io/badge/Kofi-Sponsor%20Josh%20XT-blue.svg?logo=kofi&style=plastic)](https://ko-fi.com/joshxt)

This module provides a safe way to execute Python code and shell commands in a sandboxed environment. It uses **Bubblewrap** for lightweight sandboxing without requiring Docker socket access, making it compatible with cloud platforms like Digital Ocean, AWS ECS, Google Cloud Run, and Azure Container Instances. Docker is available as an optional fallback when Bubblewrap is not available.

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

## Installation

```bash
# Basic installation (Bubblewrap sandboxing)
pip install safeexecute

# With optional Docker fallback support
pip install safeexecute[docker]
```

### System Requirements

For full sandboxing functionality, install Bubblewrap:

```bash
# Ubuntu/Debian
apt-get install bubblewrap

# Fedora/RHEL  
dnf install bubblewrap

# Alpine Linux
apk add bubblewrap
```

**Note:** If Bubblewrap is not available, SafeExecute will automatically fall back to Docker (if docker package is installed) or execute code with limited isolation.

## Features

- **No Docker Socket Required** - Works on cloud platforms without Docker-in-Docker support
- **Bubblewrap Sandboxing** - Lightweight, secure isolation without containers
- **Shell Command Support** - Execute bash commands with state persistence
- **Workspace Persistence** - Files persist between commands in conversation
- **Directory Navigation** - `cd` commands work with state preservation  
- **Multi-Conversation Isolation** - Each conversation gets its own workspace
- **Automatic Fallback** - Uses Docker when available if Bubblewrap is not installed

## Usage

You can pass an entire message from a langauge model into the `code` field and it will parse out any Python code blocks and execute them.  If anywhere in the `code` says `pip install <package>`, it will install the package in the container before executing the code.

```python
from safeexecute import execute_python_code, execute_shell_command

# Execute Python code
code = "print('Hello, World!')"
result = execute_python_code(code=code)
print(result)

# Execute shell commands (new feature!)
result = execute_shell_command("echo 'Hello from shell!'")
print(result)

# Commands maintain state (directory changes persist)
execute_shell_command("mkdir my_project")
execute_shell_command("cd my_project")
result = execute_shell_command("pwd")  # Will show /workspace/my_project
```
