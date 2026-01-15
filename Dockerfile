FROM python:3.10-bullseye
WORKDIR /app

# Install Node.js for GitHub Copilot SDK
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs

# Install Python packages
RUN pip install --upgrade pip && pip install numpy matplotlib seaborn scikit-learn yfinance scipy statsmodels sympy bokeh plotly dash networkx pyvis pandas agixtsdk openpyxl xlrd xlsxwriter

# Install GitHub Copilot CLI via npm globally
RUN npm install -g @github/copilot

# Install GitHub Copilot Python SDK
RUN pip install git+https://github.com/github/copilot-sdk.git#subdirectory=python