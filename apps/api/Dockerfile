# ── Stage 1: Python dependencies ─────────────────────────────────────────

FROM python:3.12-slim-bookworm AS python-deps

RUN pip install uv

WORKDIR /app/apps/api

COPY apps/api/pyproject.toml apps/api/uv.lock ./
COPY apps/api/src ./src

# Install all deps, then strip CUDA/nvidia packages (~3GB) and replace
# GPU torch with CPU-only torch (~220MB) in the same layer.
RUN uv venv .venv && \
    VIRTUAL_ENV=/app/apps/api/.venv uv pip install . && \
    VIRTUAL_ENV=/app/apps/api/.venv uv pip install \
      torch torchvision \
      --index-url https://download.pytorch.org/whl/cpu \
      --force-reinstall --no-deps && \
    rm -rf .venv/lib/python3.12/site-packages/nvidia* \
           .venv/lib/python3.12/site-packages/triton* \
           .venv/lib/python3.12/site-packages/cuda* && \
    find .venv -name "*.dist-info" -path "*nvidia*" -exec rm -rf {} + 2>/dev/null; \
    find .venv -name "*.dist-info" -path "*triton*" -exec rm -rf {} + 2>/dev/null; \
    find .venv -name "*.dist-info" -path "*cuda*" -exec rm -rf {} + 2>/dev/null; \
    rm -f .venv/lib/python3.12/site-packages/_cuda_bindings_redirector.pth \
          .venv/lib/python3.12/site-packages/_cuda_bindings_redirector.py; \
    true


# ── Stage 2: API service (full stack with Chromium + Node) ───────────────

FROM python:3.12-slim-bookworm AS api

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libgl1-mesa-dri \
    libgl1-mesa-glx \
    libegl1-mesa \
    fonts-liberation \
    fonts-noto-color-emoji \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

WORKDIR /app

COPY --from=python-deps /app/apps/api/.venv /app/apps/api/.venv
ENV PATH="/app/apps/api/.venv/bin:$PATH"
ENV VIRTUAL_ENV="/app/apps/api/.venv"

COPY apps/web/scripts/render-preview.mjs /app/apps/web/scripts/render-preview.mjs
RUN cd /app/apps/web/scripts && npm init -y && npm install puppeteer

COPY apps/api/pyproject.toml apps/api/uv.lock /app/apps/api/
COPY apps/api/src /app/apps/api/src

ENV RENDER_SCRIPT_PATH=/app/apps/web/scripts/render-preview.mjs

RUN mkdir -p /data
ENV PREVIEW_ARTIFACTS_DIR=/data/preview_artifacts
ENV STYLE_ARTIFACTS_DIR=/data/style_artifacts

EXPOSE 8080

CMD ["sh", "-c", "cd /app/apps/api && uvicorn smallworld_api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
