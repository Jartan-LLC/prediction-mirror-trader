# Build stage, not an inline COPY --from: Dependabot only parses FROM lines.
# Both bases are digest-pinned (tag kept beside the digest so it stays readable
# and Dependabot can resolve the next version). This image holds the trading
# wallet's private key at runtime — a floating tag is repointable by its
# publisher. See SEC-2026-0064; .github/dependabot.yml is what keeps these
# digests from going stale.
FROM ghcr.io/astral-sh/uv:0.12.13@sha256:b485bd65cc2cf1c9a93b3554012c9c3778cf7b1b5fd3d3096ce9e1226c97e1e6 AS uv-bin

FROM python:3.12-slim@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a
COPY --from=uv-bin /uv /uvx /bin/

# Node.js required for pmxt sidecar server
RUN apt-get update && apt-get install -y nodejs npm && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN uv pip install --system --no-cache .

COPY prediction_mirror/ prediction_mirror/

CMD ["python", "-m", "prediction_mirror", "run"]
