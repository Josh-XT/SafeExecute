FROM python:3.10-bullseye
WORKDIR /app

RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y nodejs gh git curl gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
RUN pip install --upgrade pip && pip install numpy matplotlib seaborn scikit-learn yfinance scipy statsmodels sympy bokeh plotly dash networkx pyvis pandas agixtsdk openpyxl xlrd xlsxwriter

# Install GitHub Copilot CLI via npm globally
RUN npm install -g @github/copilot

# Install GitHub Copilot Python SDK
RUN pip install git+https://github.com/github/copilot-sdk.git#subdirectory=python