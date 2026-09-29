# syntax=docker/dockerfile:1
# S-CORE Docs Assistant application image (specs/009-portable-deployment research R1).
# Locked dependencies, frontend built in its own stage, non-root user, no data or secrets inside.
# Base images are pinned by digest; pulling them is a preparation step.

FROM node:22-bookworm-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.12.17@sha256:10787c682e4184e4f290de1171fd4703dc63de99221f10fe1c99002ce7fa9acc AS uv

FROM python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    SCORE_ASSISTANT_CONTAINER=1 \
    PATH=/app/.venv/bin:$PATH
WORKDIR /app
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY config ./config
RUN uv sync --frozen --no-dev && rm /usr/local/bin/uv
COPY --from=frontend /build/frontend/dist ./frontend/dist
COPY THIRD_PARTY_NOTICES.md LICENSE* ./
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin score \
    && mkdir /data && chown 10001:10001 /data
USER 10001:10001
VOLUME /data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD ["python", "-c", "import sys, urllib.request as u; r = u.Request('http://127.0.0.1:8080/health/live', headers={'Host': '127.0.0.1:8080'}); sys.exit(0 if u.urlopen(r, timeout=3).status == 200 else 1)"]
ENTRYPOINT ["score-assistant", "--config", "/app/config/container.yaml"]
CMD ["serve"]
