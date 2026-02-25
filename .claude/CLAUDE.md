# Prediction Mirror Trader

## Project

Platform-agnostic prediction market mirror trading bot. Monitors target wallets via the Data API activity feed, generates signals from their trades, sizes orders using conviction-based or proportional sizing, and executes or paper-trades matching positions.

## Tech Stack

- Python 3.12, asyncio
- pmxt SDK (unified prediction market trading — auth, signing, orders, market data)
- httpx (async HTTP for Data API activity monitoring and target positions)
- web3.py (blockchain: redemption, approvals, gas)
- click (CLI framework)
- rich (terminal tables + live dashboard)
- SQLite with WAL mode (single source of truth for all state except secrets)
- python-dotenv (secret loading)

## Architecture

- **Platform-agnostic core**: the engine knows nothing about specific platforms. Each platform provides a concrete adapter behind `PlatformAdapter` ABC.
- **Activity-based signals**: monitor polls `/activity` for exact trade data (price, size, side) rather than diffing position snapshots.
- **Conviction sizing**: buy orders sized by `trade_size_pct * (1 + percentile_rank)` of available budget. Sell orders mirror the target's reduction percentage.
- **Signal aggregation**: trade fragments within a per-target window are merged before execution.
- **Sell reconciliation**: failed sells tracked as pending goals with VWAP pricing, retried each cycle. Missed buys are written off.
- **Database is the communication channel**: settings, targets, positions, trades, goals — all in SQLite. No IPC, no file watching, no signaling.
- **Data flows one direction**: Poll activity → Aggregate → Size → Execute → Persist
- **No circular dependencies**.

## Code Conventions

- **Models**: plain dataclasses in `models/`. No logic, no methods beyond `__post_init__` validation.
- **Platform adapters**: implement `PlatformAdapter` ABC from `platforms/base.py`. Each platform gets its own subdirectory.
- **Engine**: platform-agnostic. Never imports from a specific platform module.
- **Store**: all database access goes through `store/` modules. No raw SQL elsewhere.
- **Logging**: use `logging.getLogger(__name__)` in each module. No custom helper.
- **Single responsibility**: each file has one job. Its name describes that job without opening it.
- **Nested when it clarifies, flat only when genuinely simple**: directories are domain boundaries.

## Testing

- **Framework**: pytest with pytest-asyncio
- **Coverage target**: 80%+
- **TDD for core logic**: strategy sizing, activity signal parsing, executor pipeline
- **Mocks**: external APIs (Polymarket CLOB, Data API, blockchain) are mocked in tests. Never hit real endpoints.
- **Fixtures**: shared test fixtures in `tests/conftest.py`
- **Run**: `pytest --cov=prediction_mirror --cov-report=term-missing`

## Documentation

- `docs/` — permanent user-facing docs (setup, configuration, CLI, deployment)
