# Prediction Mirror Trader

A platform-agnostic bot that mirrors the trades of target wallets on prediction markets. Point it at wallets you want to follow, set budget allocations, and the bot automatically sizes and executes matching positions.

> **Status:** Dry-run mode has been tested against live Polymarket data. Live trading (real orders) has not been tested. Use at your own risk.

## Features

- **Activity-based signal detection** — polls the Polymarket activity feed for exact trade data (price, size, side) rather than position snapshots
- **Conviction-based sizing** — sizes orders relative to the target's trading behavior using percentile rank of trade values, with a configurable base trade size
- **Signal aggregation** — batches trade fragments within a configurable window before executing, preventing dust orders from partial fills
- **Sell reconciliation** — tracks failed sell orders as pending goals and retries when market conditions improve; missed buys are written off
- **Dry-run mode** — paper trades by default with simulated cash balance tracking, P&L calculations, and full dashboard
- **Live Rich dashboard** — allocation breakdown, positions with mark-to-market P&L, recent trades, signals, pending goals, and total P&L in the header
- **Platform-agnostic** — core engine works with any prediction market through adapters (Polymarket supported)
- **Live configuration** — change settings and targets via CLI while the bot is running; changes take effect on the next tick

## How It Works

```
Poll /activity → Detect trades → Aggregate fragments → Size orders → Execute → Persist
```

1. The **monitor** polls the Data API `/activity` endpoint for each target's recent trades, merging fill fragments by market within the aggregation window
2. The **strategy** sizes each signal using conviction-based sizing: `base_trade_size * (1 + percentile_rank)` of available budget, where percentile is determined from the target's historical trade values
3. The **executor** submits orders (or paper-trades in dry-run mode), retrying on transient errors. Failed sells create reconciliation goals; missed buys are written off
4. The **reconciliation loop** retries pending sell goals each cycle until slippage clears or the position is closed
5. The **redeemer** periodically checks for resolved markets and handles redemption (or calculates dry-run P&L)

## Quick Start

```bash
# Clone and install
git clone https://github.com/Jartan-LLC/prediction-mirror-trader.git
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

The bot starts in dry-run mode with a $1000 simulated balance. It will observe the target's trades, build a conviction history, and begin paper-trading once enough data is collected (configurable via `--cold-start-pct` and `--min-history`).

## CLI

```
python -m prediction_mirror [--db PATH] COMMAND

Commands:
  run [--no-dashboard]             Start the bot
  settings list                    Show all settings
  settings set KEY VALUE           Update a setting
  targets list                     Show all targets
  targets add                      Add a target
    --label --address --platform --allocation
    [--sizing-mode] [--trade-size-pct] [--aggregation-seconds]
    [--history-window] [--min-history] [--cold-start-pct]
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
  engine/          Core logic (monitor, strategy, executor, redeemer, reconciliation)
  dashboard/       Rich terminal display with live updates
  utils/           Logging, formatting, conversions
  __main__.py      Click CLI entry point
tests/             236 tests, 80%+ coverage
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

## Contributing

Contributions are welcome. This project was built as a solo effort and is unlikely to receive significant further development from the original author due to lack of financing. If you find it useful and want to improve it, please open issues or pull requests.

Areas that would benefit from contribution:
- Live trading testing and hardening
- Sizing algorithm improvements (conviction model, sell reconciliation strategy)
- Code cleanliness and refactoring (this was largely vibe-coded with AI assistance)
- Additional platform adapters (Kalshi, etc.)
- Interactive Textual-based dashboard
- Position reconciliation for missed buys
- Web UI / Telegram bot listener

## Disclaimer

This software is provided as-is, without warranty of any kind. **Only dry-run mode has been tested.** Live trading with real funds has not been validated and may result in financial loss. The authors are not responsible for any losses incurred through the use of this software. Do your own research and use at your own risk. This is not financial advice.

## License

[AGPL-3.0](LICENSE)
