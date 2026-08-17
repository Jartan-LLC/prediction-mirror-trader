# uv installs the package here, in place of pip — same tool the devcontainer
# uses. It arrives as a build stage rather than the shorter
# `COPY --from=ghcr.io/astral-sh/uv:0.12.5` because Dependabot's Dockerfile
# parser only reads `FROM` lines: an inline COPY reference is a pin nobody can
# bump. Named `uv-bin` so it does not collide with the `uv` binary below.
FROM ghcr.io/astral-sh/uv:0.12.5 AS uv-bin

FROM python:3.12-slim
COPY --from=uv-bin /uv /uvx /bin/

# Node.js required for pmxt sidecar server
RUN apt-get update && apt-get install -y nodejs npm && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# pyproject.toml alone, before the package: this layer installs the dependencies
# and caches until they change. `--system` because the container is the
# isolation; uv refuses a non-venv target without it.
COPY pyproject.toml .
RUN uv pip install --system --no-cache .

COPY prediction_mirror/ prediction_mirror/

CMD ["python", "-m", "prediction_mirror", "run"]
