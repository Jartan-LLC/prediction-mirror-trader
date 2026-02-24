# Prediction Mirror Trader

## Project

Platform-agnostic prediction market mirror trading bot. Polls target wallets for position changes, generates signals, sizes orders within budget allocations, and executes or paper-trades matching positions.

## Tech Stack

- Python 3.12, asyncio
- pmxt SDK (unified prediction market trading — auth, signing, orders, market data)
- httpx (async HTTP for Data API target monitoring)
- web3.py (blockchain: redemption, approvals, gas)
- click (CLI framework)
- rich (terminal tables + live dashboard)
- SQLite with WAL mode (single source of truth for all state except secrets)
- python-dotenv (secret loading)

## Architecture

- **Platform-agnostic core**: the engine knows nothing about specific platforms. Each platform provides a concrete adapter behind `PlatformAdapter` ABC.
- **Database is the communication channel**: settings, targets, positions, trades — all in SQLite. No IPC, no file watching, no signaling.
- **Data flows one direction**: Poll targets -> Detect changes -> Aggregate -> Size -> Execute -> Persist
- **No circular dependencies**. See `.claude/plans/phase4-design-completion.md` for the full dependency graph and revised file architecture.

## Code Conventions

- **Models**: plain dataclasses in `models/`. No logic, no methods beyond `__post_init__` validation.
- **Platform adapters**: implement `PlatformAdapter` ABC from `platforms/base.py`. Each platform gets its own subdirectory.
- **Engine**: platform-agnostic. Never imports from a specific platform module.
- **Store**: all database access goes through `store/` modules. No raw SQL elsewhere.
- **Single responsibility**: each file has one job. Its name describes that job without opening it.
- **Nested when it clarifies, flat only when genuinely simple**: directories are domain boundaries.

## Testing

- **Framework**: pytest with pytest-asyncio
- **Coverage target**: 80%+
- **TDD for core logic**: strategy sizing, position diffing (monitor), executor pipeline
- **Mocks**: external APIs (Polymarket CLOB, Gamma, blockchain) are mocked in tests. Never hit real endpoints.
- **Fixtures**: shared test fixtures in `tests/conftest.py`
- **Run**: `pytest --cov=prediction_mirror --cov-report=term-missing`

## Documentation

- `docs/` — permanent user-facing docs (setup, configuration, CLI, deployment)
- `.claude/plans/` — design specs and implementation plan (authoritative source for architecture decisions)
