# Build stage, not an inline COPY --from: Dependabot only parses FROM lines.
# Both bases are digest-pinned (tag kept beside the digest so it stays readable
# and Dependabot can resolve the next version). This image holds the trading
# wallet's private key at runtime — a floating tag is repointable by its
# publisher. See SEC-2026-0064; .github/dependabot.yml is what keeps these
# digests from going stale.
FROM ghcr.io/astral-sh/uv:0.12.17@sha256:10787c682e4184e4f290de1171fd4703dc63de99221f10fe1c99002ce7fa9acc AS uv-bin

FROM python:3.12-slim@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a
COPY --from=uv-bin /uv /uvx /bin/

# Node.js required for pmxt sidecar server
RUN apt-get update && apt-get install -y nodejs npm && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN uv pip install --system --no-cache .

COPY prediction_mirror/ prediction_mirror/

CMD ["python", "-m", "prediction_mirror", "run"]
