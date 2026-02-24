# Prediction Mirror Trader

A platform-agnostic bot that mirrors the trades of target wallets on prediction markets.

## How It Works

The bot polls target wallets for position changes, generates trading signals, sizes orders based on configurable budget allocations, and executes (or paper-trades) matching positions. The core engine is platform-agnostic — each prediction market (Polymarket, Kalshi, etc.) provides a concrete adapter behind a shared interface.

## Quick Start

1. **Open in devcontainer** (recommended):
   Open this repo in VS Code with the Dev Containers extension. The environment is fully configured.

2. **Configure secrets**:
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

3. **Run the bot**:
   ```bash
   python -m prediction_mirror run
   ```

   The bot starts in dry-run mode by default. See [docs/configuration.md](docs/configuration.md) for settings.

## Documentation

See the [docs/](docs/) directory:
- [Setup](docs/setup.md) — development environment
- [Configuration](docs/configuration.md) — settings, targets, environment variables
- [CLI](docs/cli.md) — command reference
- [Deployment](docs/deployment.md) — production deployment

## License

[AGPL-3.0](LICENSE)
