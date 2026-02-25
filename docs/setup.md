# Development Setup

## Devcontainer (recommended)

1. Open this repository in VS Code with the [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension
2. VS Code will prompt to reopen in the container — accept
3. The container installs Python 3.12, Docker, GitHub CLI, and Claude Code automatically

## Manual Setup

Requires Python 3.12+ and Node.js (for the pmxt sidecar server).

```bash
# Install in development mode
pip install -e ".[dev]"
```

## Environment

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

Required variables:
- `POLYMARKET_PRIVATE_KEY` — your Polymarket wallet private key
- `POLYMARKET_RPC_URL` — Polygon RPC endpoint (Infura, Alchemy, etc.)

## Running

```bash
# Start the bot (dry-run mode by default)
python -m prediction_mirror run

# Run without live dashboard (log output)
python -m prediction_mirror run --no-dashboard

# Run tests
pytest

# Run tests with coverage
pytest --cov=prediction_mirror --cov-report=term-missing

# Coverage gate (must stay above 80%)
pytest --cov=prediction_mirror --cov-fail-under=80

# Lint
ruff check prediction_mirror/ tests/
```

## Project Structure

```
prediction_mirror/      Main package
  models/               Domain data types (dataclasses)
  platforms/            Platform adapters (Polymarket, etc.)
  engine/               Core logic (monitor, strategy, executor, redeemer, reconciliation)
  store/                SQLite persistence
  dashboard/            Rich terminal display with live updates
  utils/                Shared utilities
tests/                  Test suite (236 tests, 80%+ coverage)
docs/                   User-facing documentation
```
