FROM python:3.11-bookworm
WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/usr/lib/python3/dist-packages

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        file \
        gh \
        git \
        gir1.2-gtk-3.0 \
        iproute2 \
        iptables \
        jq \
        less \
        libgl1 \
        libglib2.0-0 \
        libmagic1 \
        libsm6 \
        libusb-1.0-0 \
        libxext6 \
        libxrender1 \
        libzbar0 \
        nodejs \
        openssh-client \
        pkg-config \
        procps \
        python3-cairo \
        python3-gi \
        python3-wxgtk4.0 \
        ripgrep \
        sqlite3 \
        tesseract-ocr \
        unzip \
        zip \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install \
        agixtsdk \
        attrs \
        beautifulsoup4 \
        biopython \
        bokeh \
        cloakbrowser \
        dash \
        httpx \
        lxml \
        matplotlib \
        networkx \
        numpy \
        opencv-python-headless \
        openpyxl \
        pandas \
        pillow \
        plotly \
        pyOpenSSL \
        pycryptodome \
        pyjwt \
        pymupdf \
        pyotp \
        pyserial \
        pytesseract \
        python-dateutil \
        python-docx \
        python-dotenv \
        python-jose \
        python-magic \
        python-pptx \
        python-telegram-bot \
        pyusb \
        pyvis \
        pyzbar \
        pyyaml \
        qrcode \
        requests \
        scikit-image \
        scikit-learn \
        scipy \
        seaborn \
        statsmodels \
        sympy \
        xlsxwriter \
        xlrd \
        yfinance

# Install coding CLIs via npm globally
RUN npm install -g @github/copilot @openai/codex

# Install GitHub Copilot Python SDK
RUN pip install git+https://github.com/github/copilot-sdk.git#subdirectory=python
