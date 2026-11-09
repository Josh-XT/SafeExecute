#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
# Pandoc's default PDF backend is pdflatex. Keep the existing TeX/media stack;
# lmodern supplies the font package used by Pandoc's default LaTeX template.
apt-get update
apt-get install -y --no-install-recommends pandoc lmodern texlive-latex-base texlive-fonts-recommended
rm -rf /var/lib/apt/lists/*

# Isolated Python ignores the image's Debian PYTHONPATH. Install six into the
# interpreter's own site-packages for pandas/python-dateutil under python -I.
python3 -I -m pip install --no-cache-dir \
    "black==${BLACK_VERSION:-26.10.1}" \
    "pylint==${PYLINT_VERSION:-4.1.3}" \
    six==1.17.0
# Use npm's own global prefix so npx --no-install can find the binaries offline.
# These packages need no lifecycle scripts; never fetch tools at runtime.
npm install --global --ignore-scripts --no-audit --no-fund \
    "eslint@${ESLINT_VERSION:-10.14.0}" \
    "prettier@${PRETTIER_VERSION:-3.9.10}" \
    "@typescript-eslint/parser@${TYPESCRIPT_ESLINT_PARSER_VERSION:-8.72.1}"
mkdir -p /usr/local/share/safeexecute/node_modules/@typescript-eslint
ln -s "$(npm root --global)/@typescript-eslint/parser" \
    /usr/local/share/safeexecute/node_modules/@typescript-eslint/parser
npm cache clean --force
