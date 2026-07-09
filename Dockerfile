FROM python:3.11-bookworm
WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/usr/lib/python3/dist-packages \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

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
        blender \
        cmake \
        dvisvgm \
        ffmpeg \
        file \
        gh \
        git \
        gir1.2-gtk-3.0 \
        imagemagick \
        iproute2 \
        iptables \
        jq \
        latexmk \
        less \
        libasound2 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libatspi2.0-0 \
        libcairo2 \
        libcairo2-dev \
        libcups2 \
        libdbus-1-3 \
        libdrm2 \
        libgbm1 \
        libgl1 \
        libglib2.0-0 \
        libgtk-3-0 \
        libmagic1 \
        libnspr4 \
        libnss3 \
        libpango-1.0-0 \
        libpango1.0-dev \
        libsm6 \
        libssl-dev \
        libusb-1.0-0 \
        libx11-6 \
        libxcb1 \
        libxcomposite1 \
        libxdamage1 \
        libxext6 \
        libxfixes3 \
        libxkbcommon0 \
        libxrandr2 \
        libxrender1 \
        libzbar0 \
        nodejs \
        openscad \
        openssh-client \
        pkg-config \
        procps \
        python3-cairo \
        python3-gi \
        python3-wxgtk4.0 \
        ripgrep \
        sudo \
        sqlite3 \
        tesseract-ocr \
        texlive-fonts-recommended \
        texlive-latex-base \
        texlive-latex-extra \
        texlive-science \
        unzip \
        xauth \
        xvfb \
        zip \
    && rm -rf /var/lib/apt/lists/*

ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH=/usr/local/cargo/bin:$PATH

RUN curl --proto '=https' --tlsv1.2 -fsSL https://sh.rustup.rs | \
        sh -s -- -y --profile minimal --default-toolchain stable && \
    rustup component add rustfmt clippy && \
    chmod -R a+rwX /usr/local/rustup /usr/local/cargo && \
    for bin in /usr/local/cargo/bin/*; do ln -sf "$bin" "/usr/local/bin/$(basename "$bin")"; done && \
    rustc --version && \
    cargo --version

RUN groupadd -g 1000 safeexecute && \
    useradd -m -u 1000 -g safeexecute -s /bin/bash safeexecute && \
    echo "safeexecute ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/safeexecute && \
    chmod 0440 /etc/sudoers.d/safeexecute

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
        manim \
        matplotlib \
        manifold3d \
        meshio \
        networkx \
        numpy \
        numpy-stl \
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
        shapely \
        statsmodels \
        svgpathtools \
        sympy \
        trimesh \
        xlsxwriter \
        xlrd \
        yfinance

RUN python -m playwright install chromium && \
    chmod -R a+rwX /ms-playwright

# Install coding CLIs via npm globally
RUN npm install -g @github/copilot @openai/codex @anthropic-ai/claude-code

# Grok Build CLI. Runtime authentication is injected per AGiXT agent from the
# configured ~/.grok/auth.json contents, so the image only ships the binary.
RUN set -eux; \
    curl -fsSL https://x.ai/cli/install.sh | GROK_BIN_DIR=/usr/local/bin bash; \
    grok_binary="$(readlink -f /usr/local/bin/grok)"; \
    cp "$grok_binary" /usr/local/bin/grok-build-cli; \
    chmod 0755 /usr/local/bin/grok-build-cli; \
    ln -sf /usr/local/bin/grok-build-cli /usr/local/bin/grok; \
    ln -sf /usr/local/bin/grok-build-cli /usr/local/bin/agent; \
    grok --version

# Install Kiro CLI globally from the official Linux zip package. The zip path
# avoids AppImage/FUSE requirements inside Docker while matching Kiro's CLI docs.
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
        amd64) kiro_arch="x86_64" ;; \
        arm64) kiro_arch="aarch64" ;; \
        *) echo "Unsupported architecture for Kiro CLI: $arch" >&2; exit 1 ;; \
    esac; \
    curl --proto '=https' --tlsv1.2 -fsSL "https://desktop-release.q.us-east-1.amazonaws.com/latest/kirocli-${kiro_arch}-linux.zip" -o /tmp/kirocli.zip; \
    unzip -q /tmp/kirocli.zip -d /tmp; \
    Q_INSTALL_GLOBAL=1 Q_SKIP_SETUP=1 KIRO_CLI_SKIP_SETUP=1 /tmp/kirocli/install.sh; \
    rm -rf /tmp/kirocli /tmp/kirocli.zip

# Install GitHub Copilot Python SDK
RUN pip install git+https://github.com/github/copilot-sdk.git#subdirectory=python
