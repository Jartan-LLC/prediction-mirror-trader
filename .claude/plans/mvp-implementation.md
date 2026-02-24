# Implementation Plan: Prediction Mirror Trader — MVP

Pre-planning Phases 1-4 are complete. This is the final implementation plan.

**Supporting documents:**
- `.claude/plans/phase1-gap-audit.md` — 49 gaps identified
- `.claude/plans/phase2-stack-research.md` — all stack decisions + API research
- `.claude/plans/phase4-design-completion.md` — all gap resolutions, revised architecture, specs

---

## MVP Definition

The bot is MVP-complete when:
1. `python -m prediction_mirror run` starts and runs in dry-run mode
2. Engine polls target wallets via Data API, detects position changes, generates signals
3. Strategy sizes orders within allocation budgets
4. Dry-run mode paper-trades (persists to SQLite)
5. CLI commands work: `settings list/set`, `targets list/add/enable/disable/remove/set-allocation`
6. Dashboard renders live status via `rich`
7. `settings set dry_run false` enables live trading via pmxt
8. `pytest --cov=prediction_mirror --cov-fail-under=80` passes
9. `docker compose up -d` starts the bot

---

## Tech Stack

| Component | Choice |
|-----------|--------|
| Polymarket SDK | pmxt v2.14+ (handles auth, signing, orders, market data) |
| Target monitoring | httpx → Data API (`GET /positions?user={addr}`) |
| Blockchain | web3.py (redemption, approvals, gas) |
| CLI | click |
| Terminal output | rich (tables, live dashboard) |
| DB | sqlite3 (stdlib, WAL mode) |
| Settings type | Typed dataclass |
| Testing | pytest + respx + unittest.mock |

---

## Implementation Phases

### Phase 1: Foundation — Models + Utils + Dependencies

**Files:** `pyproject.toml`, `utils/*`, `models/*`, `tests/conftest.py`, `tests/test_models.py`, `tests/test_utils.py`

**pyproject.toml dependencies:**
```toml
dependencies = [
    "pmxt>=2.14",
    "httpx>=0.27",
    "web3>=6.0",
    "python-dotenv>=1.0",
    "click>=8.0",
    "rich>=13.0",
]
```

**Models (7 files):** All dataclasses per `docs/reference/models.md` + new `models/settings.py` (Settings dataclass). `models/__init__.py` re-exports all.

**Utils (3 files):** `log.py` (structured logging, rotating file), `formatting.py` (fmt_usd, fmt_address, fmt_timestamp, fmt_pct), `conversions.py` (USDC decimals, clamp).

**Tests:** Model construction, validation, utils formatting.

**Done when:** `pytest tests/test_models.py tests/test_utils.py` passes.

---

### Phase 2: Store Layer

**Files:** `store/database.py`, `store/settings.py`, `store/targets.py`, `store/snapshots.py`, `store/signals.py`, `store/trades.py`, `store/portfolio.py`, `store/__init__.py`, `tests/test_store_*.py`

**Key details:**
- `database.py`: Module-level singleton, WAL mode, `check_same_thread=False`
- `settings.py`: `get_current()` returns typed `Settings` dataclass
- `store/__init__.py`: `Store` facade class grouping all modules with shared connection
- Schema: exactly as in `docs/reference/store.md` + `realized_pnl` column on `our_positions`
- Transaction boundaries: `with conn:` for atomic trade+position updates

**Tests:** In-memory SQLite. CRUD round-trips, allocation validation, transaction atomicity.

**Done when:** All store tests pass.

---

### Phase 3: Platform Adapter

**Files:** `platforms/base.py`, `platforms/errors.py`, `platforms/__init__.py`, `platforms/polymarket/config.py`, `platforms/polymarket/data_api.py`, `platforms/polymarket/blockchain.py`, `platforms/polymarket/adapter.py`, `platforms/polymarket/__init__.py`, `tests/test_platform_polymarket.py`

**Key details:**
- `base.py`: Updated ABC with `get_price(asset_id, side)` and `fetch_target_positions(address)`
- `errors.py`: `PlatformError`, `TransientError`, `FatalError`
- `data_api.py`: httpx async client for `GET https://data-api.polymarket.com/positions?user={addr}` + market resolution status. Maps Data API response to `TargetPosition` models.
- `blockchain.py`: web3.py for MATIC balance, USDC/CTF approvals, `redeemPositions()`. Contract addresses hardcoded.
- `adapter.py`: Wraps `pmxt.Polymarket` for trading ops. Uses `asyncio.to_thread()` for sync pmxt calls. Composes `data_api` and `blockchain` for target monitoring and chain ops.

**Tests:** Mock pmxt with `unittest.mock.patch`, mock httpx with `respx`, mock web3 with `unittest.mock`. Test: position parsing, order submission, error classification.

**Done when:** Adapter tests pass with all externals mocked.

---

### Phase 4: Engine Core (TDD)

**Files:** `engine/listener.py`, `engine/monitor.py`, `engine/strategy.py`, `engine/executor.py`, `engine/redeemer.py`, `engine/core.py`, `tests/test_engine_*.py`

**TDD order — tests FIRST for monitor and strategy:**

1. Write `tests/test_engine_monitor.py` (diff_positions: 6 cases)
2. Implement `engine/monitor.py`
3. Write `tests/test_engine_strategy.py` (size_order: 10+ cases)
4. Implement `engine/strategy.py`
5. Implement `engine/listener.py` (EngineListener protocol)
6. Implement `engine/executor.py`
7. Write `tests/test_engine_executor.py`
8. Implement `engine/redeemer.py`
9. Write `tests/test_engine_redeemer.py`
10. Implement `engine/core.py`

**Key details:**
- `monitor.py`: `diff_positions()` is pure (no I/O). `poll_target()` is async (calls adapter).
- `strategy.py`: `size_order()` is pure. Buy = budget-ratio. Sell = percentage-mirror. Slippage check = `abs(current - signal) / signal > tolerance`.
- `executor.py`: Per-signal processing. Retry with exponential backoff (3 attempts). Atomic persistence via `with conn:`.
- `redeemer.py`: Checks resolved markets. Real → `adapter.redeem_if_needed()`. Dry-run → calculate P&L, record as REDEEM trade.
- `core.py`: Two async loops (monitor + redeemer). Per-target try/except (never crash). SIGINT → graceful shutdown.

**Done when:** All engine tests pass, 90%+ coverage on engine/.

---

### Phase 5: Dashboard + CLI

**Files:** `dashboard/*`, `__main__.py`, `tests/test_cli_*.py`, `tests/test_dashboard_views.py`

**Key details:**
- Dashboard uses `rich.live.Live` for auto-refresh
- `DashboardListener` implements EngineListener, queues events, triggers re-renders
- CLI uses `click` command groups: `@cli.group()` for settings and targets
- Output via `rich.table.Table` and `rich.console.Console`
- Startup sequence: dotenv → parse args → init_db → build adapters → start engine → attach dashboard → run
- SIGINT/SIGTERM → `engine.shutdown()`

**Done when:** `python -m prediction_mirror --help` works. CLI tests pass.

---

### Phase 6: Integration + Polish

**Files:** `tests/test_integration.py`, Dockerfile update, docker-compose.yml update

**Integration test:** Spin up engine with mocked adapter. Simulate 3 poll ticks with position changes. Assert full pipeline: signal → size → paper-trade → persist → dashboard event.

**Docker:** Add Node.js to Dockerfile (pmxt sidecar requirement). Set `PMT_DB_PATH=/app/data/mirror.db`.

**Coverage gate:** `pytest --cov=prediction_mirror --cov-fail-under=80`

**Cleanup:** Delete `docs/reference/` (temporary build-phase specs).

**Done when:** Tests pass at 80%+, Docker starts, reference docs deleted.

---

## File Delivery Order

```
Phase 1:  pyproject.toml
          utils/log.py, utils/formatting.py, utils/conversions.py, utils/__init__.py
          models/market.py, models/position.py, models/signal.py, models/order.py
          models/wallet.py, models/target.py, models/settings.py, models/__init__.py
          tests/conftest.py, tests/test_models.py, tests/test_utils.py

Phase 2:  store/database.py, store/settings.py, store/targets.py
          store/snapshots.py, store/signals.py, store/trades.py, store/portfolio.py
          store/__init__.py
          tests/test_store_settings.py, tests/test_store_targets.py
          tests/test_store_portfolio.py, tests/test_store_snapshots.py

Phase 3:  platforms/errors.py, platforms/base.py, platforms/__init__.py
          platforms/polymarket/config.py, platforms/polymarket/data_api.py
          platforms/polymarket/blockchain.py, platforms/polymarket/adapter.py
          platforms/polymarket/__init__.py
          tests/test_platform_polymarket.py

Phase 4:  engine/listener.py
          tests/test_engine_monitor.py → engine/monitor.py
          tests/test_engine_strategy.py → engine/strategy.py
          engine/executor.py → tests/test_engine_executor.py
          engine/redeemer.py → tests/test_engine_redeemer.py
          engine/core.py

Phase 5:  dashboard/activity_view.py, dashboard/portfolio_view.py
          dashboard/renderer.py, dashboard/listener.py, dashboard/__init__.py
          __main__.py
          tests/test_cli_settings.py, tests/test_cli_targets.py
          tests/test_dashboard_views.py

Phase 6:  tests/test_integration.py
          Dockerfile (add Node.js)
          docker-compose.yml (update PMT_DB_PATH)
          delete docs/reference/
```

---

## Risks

| Risk | Mitigation |
|------|------------|
| pmxt sidecar crashes during long-running bot | pmxt auto-restarts sidecar; add health check in adapter.initialize() |
| Data API rate limits (150/10s for positions) | Sequential polling with 2s interval; 10 targets = 50/10s (within limit) |
| pmxt sync blocking event loop | All pmxt calls wrapped in `asyncio.to_thread()` |
| Node.js requirement in Docker | Multi-stage build or slim image with both runtimes |
| Polymarket API schema changes | All API interaction isolated in `platforms/polymarket/`; easy to patch |
| SQLite concurrent access | WAL mode + `check_same_thread=False` |

---

## Pre-Planning Checklist

- [x] Phase 1: Gap audit — 49 gaps documented
- [x] Phase 2: Stack decisions — pmxt, httpx, click, rich, sqlite3 WAL
- [x] Phase 3: API research — Data API schema, contract addresses, rate limits, CLOB auth
- [x] Phase 4: Design completion — all gaps resolved, architecture updated, specs written
- [x] Phase 5: Implementation plan — this document
