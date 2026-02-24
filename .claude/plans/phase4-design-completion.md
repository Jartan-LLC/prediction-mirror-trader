# Phase 4: Design Completion

Status: IN PROGRESS

Resolves all blocking gaps from Phase 1, incorporating stack decisions from Phase 2.

---

## Gap Resolutions

### Gap #5: Market model has no asset_id mapping

**Resolution:** The Data API returns `asset` (token ID) and `outcome` per position. pmxt's `MarketOutcome.outcome_id` IS the CLOB Token ID (asset_id) for Polymarket. The `UnifiedMarket.outcomes` list provides the mapping:

```python
# From pmxt: market.outcomes[0].outcome_id = "Yes" token ID
# From pmxt: market.outcomes[1].outcome_id = "No" token ID
```

**No model change needed.** The adapter maps `MarketOutcome.outcome_id` → our `asset_id` and `MarketOutcome.label` → our `outcome`. The `Market` model doesn't need `asset_ids` because the adapter resolves this at query time.

For redemption, we use `conditionId` from the Data API response, not `market_id`. The adapter stores `conditionId` as `market_id` for Polymarket (it's the true identifier).

### Gap #6/#17: get_price side ambiguity

**Resolution:** Change `PlatformAdapter.get_price()` signature to accept a `side` parameter:

```python
@abstractmethod
async def get_price(self, asset_id: str, side: str) -> float:
    """Get current price for asset. side is 'buy' or 'sell'."""
```

Implementation: pmxt's `fetch_order_book(outcome_id)` returns `OrderBook(bids, asks)`. For buy, return `asks[0].price` (best ask). For sell, return `bids[0].price` (best bid). Falls back to midpoint if book is empty on one side.

### Gap #7: OrderResult doesn't carry signal_id

**Resolution:** `signal_id` is NOT part of the OrderResult model. It's threaded through the executor:

```python
# In executor.handle_signals():
signal_id = store.signals.insert_signal(signal)  # returns int
sized_order = strategy.size_order(signal, ...)
if sized_order:
    result = await execute_order(sized_order, adapter)
    store.trades.insert_trade(result, signal_id)  # passed alongside
```

The signal_id is a local variable in the executor loop, not embedded in the order. No model change needed.

### Gap #8/#30: Settings typed model

**Resolution:** Defined in Phase 2. `Settings` is a dataclass in `models/settings.py`:

```python
@dataclass
class Settings:
    poll_interval_seconds: int = 2
    slippage_tolerance_pct: float = 2.0
    min_order_usd: float = 1.0
    max_order_usd: float = 500.0
    max_position_usd: float = 1000.0
    aggregation_window_seconds: int = 0
    redeemer_interval_seconds: int = 7200
    dashboard_refresh_seconds: int = 30
    dry_run: bool = True
    log_level: str = "INFO"
```

`store/settings.py:get_current(conn)` reads key-value strings, casts to proper types, returns `Settings`. Coercion happens here and nowhere else.

Add to `models/__init__.py` re-exports. Add to `docs/reference/models.md`.

### Gap #9: TargetPosition.avg_price source

**Resolution:** The Data API `GET /positions` returns `avgPrice` per position. This is calculated by Polymarket server-side. We pass it through directly. No calculation needed on our end.

### Gap #10: OurPosition.total_cost update logic

**Resolution:** On buy fill:
```python
new_total_cost = position.total_cost + (fill_size * fill_price)
new_size = position.size + fill_size
new_avg_entry = new_total_cost / new_size
```

On sell fill:
```python
# Reduce proportionally — selling doesn't change avg_entry_price
new_size = position.size - fill_size
new_total_cost = new_size * position.avg_entry_price
```

This logic lives in the executor after persisting the trade result.

### Gap #14: fetch_target_portfolio_value definition

**Resolution:** For Polymarket, target portfolio value = sum of all their position values (size * current_price) across all markets. This is calculated from the Data API positions response:

```python
portfolio_value = sum(pos["size"] * pos["curPrice"] for pos in positions)
```

Does NOT include liquid USDC balance (we can't see other users' USDC). This is acceptable because the strategy's ratio calculation `target_budget / target_portfolio_value` only needs to express our budget as a proportion of the target's exposure, not their total wealth.

### Gap #15: redeem_if_needed conditionId mapping

**Resolution:** The adapter stores `conditionId` (from Data API) as the `market_id` in our models for Polymarket. This is the native market identifier on Polymarket. The `redeem_if_needed` method receives `market_id` which is already the `conditionId`.

### Gap #16: Error taxonomy

**Resolution:**

```python
class PlatformError(Exception):
    """Base for all platform adapter errors."""

class TransientError(PlatformError):
    """Retryable: network timeout, 429 rate limit, 5xx server error."""

class FatalError(PlatformError):
    """Not retryable: invalid order, insufficient funds, auth failure, 4xx."""
```

The adapter wraps pmxt exceptions and httpx errors into these categories. The executor retries on `TransientError`, logs and skips on `FatalError`.

### Gap #20: Slippage check definition

**Resolution:**

```python
def check_slippage(signal_price: float, current_price: float, tolerance_pct: float) -> bool:
    """Returns True if slippage is acceptable."""
    if signal_price <= 0:
        return True  # No reference price
    slippage_pct = abs(current_price - signal_price) / signal_price * 100
    return slippage_pct <= tolerance_pct
```

- `signal_price` = price when the signal was detected (`signal.target_price`)
- `current_price` = price at order time (`adapter.get_price(asset_id, side)`)
- `tolerance_pct` = `settings.slippage_tolerance_pct` (default 2.0%)

If the price moved more than the tolerance between detection and execution, the order is skipped.

### Gap #21: Aggregation window behavior

**Resolution:** **Defer for MVP.** The `aggregation_window_seconds` setting exists (default 0), but the aggregation logic is not needed at MVP. At `0`, signals are processed immediately with no batching. The `aggregate_signals` function simply passes signals through unchanged.

A future version could batch signals within a window to combine multiple small position changes into a single order. For now, document this as "reserved for future use" and implement the pass-through.

### Gap #22: Error handling in loops

**Resolution:** Per-target try/except in the monitor loop:

```python
async def _monitor_loop(self):
    while self._running:
        settings = store.settings.get_current(conn)
        targets = store.targets.get_enabled(conn)
        for target in targets:
            try:
                signals = await monitor.poll_target(target, adapter, store)
                if signals:
                    await executor.handle_signals(signals, adapters, store, settings)
            except TransientError as e:
                self._dispatch("on_error", str(e), {"target": target.label, "transient": True})
            except Exception as e:
                self._dispatch("on_error", str(e), {"target": target.label, "transient": False})
                logger.exception(f"Error polling target {target.label}")
        await asyncio.sleep(settings.poll_interval_seconds)
```

Key: **never crash the loop.** Log the error, dispatch to listeners, continue to next target.

### Gap #23: Engine store parameter type

**Resolution:** The `store` parameter is a module-namespace-like object. In practice, we create a simple container:

```python
@dataclass
class Store:
    """Facade grouping all store modules with a shared connection."""
    conn: sqlite3.Connection
    settings: module  # store.settings
    targets: module   # store.targets
    snapshots: module # store.snapshots
    signals: module   # store.signals
    trades: module    # store.trades
    portfolio: module # store.portfolio
```

Or more practically, `store/__init__.py` creates and exports this facade:

```python
# store/__init__.py
class Store:
    def __init__(self, conn):
        self.conn = conn
    # Methods delegate to submodules, passing self.conn
```

This keeps the engine from needing to know about `sqlite3.Connection` directly.

### Gap #24: Portfolio value and dry-run positions

**Resolution:** Portfolio value for budget calculation uses **real capital only**:

```python
portfolio_value = wallet_balance + sum(
    pos.size * current_price
    for pos in store.portfolio.get_all_positions(dry_run=False)
)
```

Dry-run positions are tracked separately and don't affect budget allocation. This means in dry-run mode, `portfolio_value` starts at the initial wallet balance and stays there (since no real trades consume capital). This is correct — paper trading uses a budget based on what you actually have.

### Gap #25: Sequential vs concurrent target polling

**Resolution:** Sequential for MVP. With 2-5 targets and ~200ms per API call, each poll cycle takes <1 second. Acceptable for MVP. Can add `asyncio.gather()` in a future version for scalability.

### Gap #27: Retry policy

**Resolution:**
- Max attempts: 3
- Backoff: exponential (1s, 2s, 4s)
- Retryable: `TransientError` (network, 429, 5xx)
- Fatal (no retry): `FatalError` (4xx except 429, invalid params, insufficient funds)
- Timeout per attempt: 10 seconds

### Gap #28-29: Connection management + WAL

**Resolution:**

```python
# store/database.py
_connection: sqlite3.Connection | None = None

def init_db(path: str | Path) -> sqlite3.Connection:
    global _connection
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    _create_tables(conn)
    settings.seed_defaults(conn)
    conn.commit()
    _connection = conn
    return conn

def get_connection() -> sqlite3.Connection:
    if _connection is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _connection

def close() -> None:
    global _connection
    if _connection:
        _connection.close()
        _connection = None
```

Module-level singleton. `check_same_thread=False` because the engine's asyncio loop and potential `to_thread` calls may touch it from different threads (WAL mode makes this safe for our access pattern).

### Gap #31: Transaction boundaries

**Resolution:** The executor wraps trade persistence in a transaction:

```python
def persist_trade_result(conn, result, signal_id, position_update):
    """Atomic: insert trade + update position."""
    with conn:  # sqlite3 context manager = transaction
        trades.insert_trade(conn, result, signal_id)
        portfolio.upsert_position(conn, position_update)
```

Using Python's `with conn:` pattern, which auto-commits on success and auto-rollbacks on exception.

### Gap #35: P&L persistence

**Resolution:** Add a `realized_pnl` column to `our_positions`:

```sql
ALTER TABLE our_positions ADD COLUMN realized_pnl REAL NOT NULL DEFAULT 0;
```

When the redeemer resolves a position, it updates `realized_pnl` before zeroing out the position. The trade summary can aggregate realized P&L across all positions.

Also add a new `pnl_events` concept to `executed_trades` by recording the redemption as a special trade with `side='REDEEM'`.

### Gap #36: store/__init__.py role

**Resolution:** `store/__init__.py` exports the `Store` facade class (see Gap #23 resolution). All callers import from `prediction_mirror.store`:

```python
from prediction_mirror.store import Store
store = Store(conn)
store.settings.get_current()  # delegates to store.settings module
```

---

## Revised File Architecture

With pmxt and all decisions applied:

```
prediction_mirror/
├── __init__.py
├── __main__.py                            CLI entry (click)
│
├── models/
│   ├── __init__.py                        Re-exports
│   ├── market.py                          Market, MarketStatus
│   ├── position.py                        TargetPosition, OurPosition
│   ├── signal.py                          Signal, SignalType
│   ├── order.py                           SizedOrder, OrderResult, OrderSide
│   ├── wallet.py                          WalletState
│   ├── target.py                          TargetConfig
│   └── settings.py                        Settings dataclass (NEW)
│
├── platforms/
│   ├── __init__.py                        Registry
│   ├── base.py                            PlatformAdapter ABC
│   ├── errors.py                          PlatformError, TransientError, FatalError (NEW)
│   └── polymarket/
│       ├── __init__.py
│       ├── config.py                      Constants + env loading
│       ├── adapter.py                     PolymarketAdapter (wraps pmxt)
│       ├── data_api.py                    Data API: target positions + market status (RENAMED)
│       └── blockchain.py                  Web3: gas, approvals, redemption (SIMPLIFIED)
│
├── engine/
│   ├── __init__.py
│   ├── core.py                            Engine: lifecycle, loops, dispatch
│   ├── listener.py                        EngineListener protocol
│   ├── monitor.py                         Poll + diff + signal generation
│   ├── strategy.py                        Allocation-aware sizing
│   ├── executor.py                        Aggregation, submission, retries, dry-run
│   └── redeemer.py                        Resolved-market redemption + dry-run P&L
│
├── store/
│   ├── __init__.py                        Store facade class
│   ├── database.py                        Connection, schema, WAL
│   ├── settings.py                        Settings CRUD
│   ├── targets.py                         Targets CRUD
│   ├── snapshots.py                       Target position snapshots
│   ├── signals.py                         Signal audit log
│   ├── trades.py                          Trade records
│   └── portfolio.py                       Our positions + allocation
│
├── dashboard/
│   ├── __init__.py
│   ├── listener.py                        DashboardListener (EngineListener impl)
│   ├── renderer.py                        rich.live.Live dashboard
│   ├── portfolio_view.py                  Positions + allocation (rich.table)
│   └── activity_view.py                   Signals + trades (rich.table)
│
└── utils/
    ├── __init__.py
    ├── log.py                             Structured logging
    ├── formatting.py                      USD, address, timestamp formatting
    └── conversions.py                     USDC decimals, clamping
```

**Changes from original plan:**
- Added `models/settings.py`
- Added `platforms/errors.py`
- Renamed `platforms/polymarket/positions_api.py` → `data_api.py`
- Removed `platforms/polymarket/orderbook.py` (pmxt handles this)
- File count: 30 files across 7 directories (was 29)

---

## Updated PlatformAdapter ABC

```python
class PlatformAdapter(ABC):
    # ── Lifecycle ──
    @abstractmethod
    async def initialize(self) -> None: ...
    async def shutdown(self) -> None: ...

    # ── Factory ──
    @classmethod
    @abstractmethod
    def from_env(cls) -> "PlatformAdapter": ...

    # ── Read: Targets ──
    @abstractmethod
    async def fetch_target_positions(self, address: str) -> list[TargetPosition]: ...
    @abstractmethod
    async def fetch_target_portfolio_value(self, address: str) -> float: ...

    # ── Read: Markets ──
    @abstractmethod
    async def fetch_market(self, market_id: str) -> Market: ...
    @abstractmethod
    async def get_price(self, asset_id: str, side: str) -> float: ...
    #                                          ^^^^ NEW: 'buy' or 'sell'

    # ── Read: Our Wallet ──
    @abstractmethod
    async def get_wallet_state(self) -> WalletState: ...

    # ── Write: Trading ──
    @abstractmethod
    async def submit_order(self, order: SizedOrder) -> OrderResult: ...
    async def cancel_order(self, order_id: str) -> bool: ...
    async def redeem_if_needed(self, market_id: str, position: OurPosition) -> bool: ...

    # ── Metadata ──
    @property
    @abstractmethod
    def platform_name(self) -> str: ...
    @property
    @abstractmethod
    def currency_decimals(self) -> int: ...
```

**Changes:** `get_price` now takes `side` parameter. `fetch_positions` renamed to `fetch_target_positions` for clarity.

---

## Startup Sequence

```
1. load_dotenv()
2. Parse CLI args (click)
3. Resolve DB path (--db flag > PMT_DB_PATH env > ./prediction_mirror.db)
4. init_db(path) → creates tables, seeds defaults, enables WAL
5. For each platform in enabled targets:
     adapter = get_adapter_class(platform).from_env()
     await adapter.initialize()  # pmxt server starts, checks approvals
6. engine = Engine(store, adapters)
7. dashboard = DashboardListener(store)
8. engine.add_listener(dashboard)
9. Register SIGINT/SIGTERM handler → engine.shutdown()
10. await engine.run()  # blocks until shutdown
11. store.close()
```

---

## Graceful Shutdown

```python
async def shutdown(self):
    self._running = False
    # Cancel monitor and redeemer tasks
    for task in self._tasks:
        task.cancel()
    # Wait for tasks to finish (with timeout)
    await asyncio.gather(*self._tasks, return_exceptions=True)
    # Shutdown adapters
    for adapter in self._adapters.values():
        await adapter.shutdown()
    self._dispatch("on_status_change", "stopped", "Shutdown complete")
```

SIGINT/SIGTERM registered via `asyncio.get_event_loop().add_signal_handler()`.

---

## Dashboard Layout (rich)

```
┌─────────────────────────────────────────────────────┐
│  PREDICTION MIRROR TRADER  [DRY RUN]  3 targets     │
│  Uptime: 2h 14m  |  Last poll: 3s ago               │
├─────────────────────────────────────────────────────┤
│  ALLOCATION                                          │
│  Target         Alloc   Budget    Deployed  Avail    │
│  Whale Alpha    50%     $500.00   $312.50   $187.50  │
│  Smart Money    30%     $300.00   $0.00     $300.00  │
│  Degen Fund     20%     $200.00   $89.00    $111.00  │
│  Reserve        —       —         —         $0.00    │
├─────────────────────────────────────────────────────┤
│  POSITIONS (3)                                       │
│  Market              Outcome  Size   Entry  Current  │
│  Will Trump win...   Yes      15.0   $0.52  $0.55    │
│  Fed rate cut...     No       8.0    $0.35  $0.32    │
│  Bitcoin > 100k...   Yes      20.0   $0.68  $0.71    │
├─────────────────────────────────────────────────────┤
│  RECENT ACTIVITY                                     │
│  14:05 BUY  Whale Alpha  "Will Trump..."  +10 @ $0.52│
│  14:02 SELL Smart Money  "Fed rate..."    -5 @ $0.35  │
│  13:58 BUY  Whale Alpha  "Bitcoin >..."  +20 @ $0.68  │
├─────────────────────────────────────────────────────┤
│  ERRORS (0)                                          │
└─────────────────────────────────────────────────────┘
```

Rendered via `rich.live.Live` with `rich.table.Table` for each section. Refreshes every `dashboard_refresh_seconds` (default 30s) or immediately on signal/trade events.

---

## CLI Spec (click)

```
prediction_mirror [--db PATH]

Commands:
  run                          Start the bot
  settings list                Show all settings
  settings set KEY VALUE       Update a setting
  targets list                 Show all targets with allocation
  targets add                  Add a new target
    --label TEXT (required)
    --address TEXT (required)
    --platform TEXT (required)
    --allocation FLOAT (required)
    --multiplier FLOAT (default 1.0)
    --enabled / --disabled (default enabled)
  targets enable LABEL         Enable a target
  targets disable LABEL        Disable a target
  targets remove LABEL         Remove a target
  targets set-allocation LABEL PCT  Change allocation
```

Output: `rich.table.Table` for list commands. `rich.console.Console` for messages.

Error handling: Invalid key → "Unknown setting: {key}". Allocation > 100% → "Total allocation would exceed 100% ({sum}%)". Missing env vars → "POLYMARKET_PRIVATE_KEY not set. See docs/configuration.md".

---

## Logging Spec

```python
# utils/log.py
import logging
from logging.handlers import RotatingFileHandler

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_FILE = "prediction_mirror.log"
MAX_BYTES = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 3

def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger("prediction_mirror")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Console handler (INFO+ by default)
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(console)

    # File handler (DEBUG+, rotating)
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(file_handler)

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"prediction_mirror.{name}")
```

---

## Test Strategy

| Module | Test Type | Mock Layer | Key Cases |
|--------|-----------|-----------|-----------|
| `models/` | Unit | None | Construction, validation, edge cases |
| `utils/` | Unit | None | Formatting, conversions |
| `store/` | Integration | In-memory SQLite | CRUD round-trips, constraints, transactions |
| `engine/monitor` | Unit (TDD) | None (pure `diff_positions`) | All 5 diff cases + dust threshold |
| `engine/strategy` | Unit (TDD) | None (pure `size_order`) | All buy/sell algorithm branches |
| `engine/executor` | Unit | Mock adapter + store | Signal→order flow, dry-run, retry |
| `engine/redeemer` | Unit | Mock adapter + store | Real + dry-run P&L calculation |
| `engine/core` | Integration | Mock adapter | Full tick cycle |
| `platforms/polymarket` | Unit | Mock pmxt + httpx + web3 | Adapter method mapping, error handling |
| `dashboard/` | Unit | Mock store data | Render functions return strings |
| `__main__` | Integration | In-memory SQLite | CLI subcommand parsing + execution |
| Integration | End-to-end | Mock adapter (3 ticks) | Full pipeline: poll→signal→size→execute→persist |

**Coverage target:** 80%+ overall. Engine and store modules targeted at 90%+.

---

## Schema Addition

Add `realized_pnl` to `our_positions`:

```sql
CREATE TABLE IF NOT EXISTS our_positions (
    market_id       TEXT    NOT NULL,
    asset_id        TEXT    NOT NULL,
    platform        TEXT    NOT NULL,
    outcome         TEXT    NOT NULL,
    size            REAL    NOT NULL DEFAULT 0,
    avg_entry_price REAL    NOT NULL DEFAULT 0,
    total_cost      REAL    NOT NULL DEFAULT 0,
    realized_pnl    REAL    NOT NULL DEFAULT 0,   -- NEW
    source_target   TEXT    NOT NULL,
    dry_run         INTEGER NOT NULL DEFAULT 0,
    updated_at      TEXT    NOT NULL,
    PRIMARY KEY (market_id, asset_id, source_target)
);
```
