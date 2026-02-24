# Prediction Mirror Trader

A platform-agnostic bot that mirrors the trades of target wallets on prediction markets. Point it at wallets you want to follow, set budget allocations, and the bot automatically sizes and executes matching positions.

## Features

- **Mirror trading** — polls target wallets for position changes, generates signals, sizes orders within budget allocations
- **Platform-agnostic** — core engine works with any prediction market through adapters (Polymarket supported)
- **Allocation-aware sizing** — each target gets a percentage of your capital; buy orders scale proportionally, sell orders mirror the target's percentage reduction
- **Dry-run mode** — paper trades by default, persisting simulated positions to SQLite for review before going live
- **Live configuration** — change settings and targets via CLI while the bot is running; changes take effect on the next tick
- **Rich terminal dashboard** — allocation breakdown, positions, recent activity, and errors
- **SQLite state** — all state (settings, targets, positions, trades, signals) lives in a single database file

## How It Works

```
Poll targets → Detect changes → Generate signals → Size orders → Execute → Persist
```

1. The **monitor** polls each target wallet via the Data API, diffs against the last snapshot, and emits BUY/SELL signals
2. The **strategy** sizes each signal relative to your budget allocation for that target, respecting per-order and per-position caps
3. The **executor** submits orders (or paper-trades in dry-run mode), retrying on transient errors
4. The **redeemer** periodically checks for resolved markets and handles redemption (or calculates dry-run P&L)

The engine reads settings and targets from the database on every tick — no restart needed for configuration changes.

## Quick Start

```bash
# Clone and install
git clone https://github.com/YOUR_USER/prediction-mirror-trader.git
cd prediction-mirror-trader
pip install -e ".[dev]"

# Configure secrets
cp .env.example .env
# Edit .env with your Polymarket private key and RPC URL

# Add a target to mirror
python -m prediction_mirror targets add \
    --label "Whale Alpha" \
    --address "0x..." \
    --platform polymarket \
    --allocation 50

# Start the bot (dry-run mode by default)
python -m prediction_mirror run
```

## CLI

```
python -m prediction_mirror [--db PATH] COMMAND

Commands:
  run                              Start the bot
  settings list                    Show all settings
  settings set KEY VALUE           Update a setting
  targets list                     Show all targets
  targets add --label --address    Add a target
    --platform --allocation
  targets enable LABEL             Enable a target
  targets disable LABEL            Disable a target
  targets remove LABEL             Remove a target
  targets set-allocation LABEL %   Change allocation
```

See [docs/cli.md](docs/cli.md) for the full reference.

## Project Structure

```
prediction_mirror/
  models/          Domain data types (7 dataclasses)
  store/           SQLite persistence (WAL mode)
  platforms/       Platform adapters (Polymarket)
  engine/          Core logic (monitor, strategy, executor, redeemer)
  dashboard/       Rich terminal display
  utils/           Logging, formatting, conversions
  __main__.py      Click CLI entry point
tests/             214 tests at 88% coverage
docs/              User-facing documentation
```

## Testing

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=prediction_mirror --cov-report=term-missing

# Coverage gate (CI)
pytest --cov=prediction_mirror --cov-fail-under=80
```

## Documentation

- [Setup](docs/setup.md) — development environment
- [Configuration](docs/configuration.md) — settings, targets, environment variables
- [CLI Reference](docs/cli.md) — all commands
- [Deployment](docs/deployment.md) — Docker, production setup

## License

[AGPL-3.0](LICENSE)
