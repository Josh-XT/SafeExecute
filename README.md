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
