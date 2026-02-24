# Development Setup

## Devcontainer (recommended)

1. Open this repository in VS Code with the [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension
2. VS Code will prompt to reopen in the container — accept
3. The container installs Python 3.12, Docker, GitHub CLI, and Claude Code automatically

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

# Run tests
pytest

# Run tests with coverage
pytest --cov=prediction_mirror --cov-report=term-missing
```

## Project Structure

```
prediction_mirror/      Main package
  models/               Domain data types (dataclasses)
  platforms/            Platform adapters (Polymarket, etc.)
  engine/               Core logic (platform-agnostic)
  store/                SQLite persistence
  dashboard/            CLI status display
  utils/                Shared utilities
tests/                  Test suite
docs/                   Documentation
```
