# Design Specs (Consolidated & Updated)

Consolidated from the original `docs/reference/` specs with all gap resolutions and
planning decisions integrated. This is the single authoritative design reference.

For decision rationale, see `phase2-stack-research.md` (stack) and `phase4-design-completion.md` (gap resolutions).

---

## Architecture

### Design Philosophy

**Nested when it clarifies, flat only when genuinely simple.** Every directory is a domain boundary. Every file has one job, and its name says what that job is without opening it.

**Platform-agnostic core.** The engine knows nothing about Polymarket, Kalshi, or any specific platform. It works with abstract positions, orders, and markets. Each platform provides a concrete adapter behind a shared interface.

**Budget allocation is first-class.** Each target gets a percentage of total capital. The strategy sizes every order within that envelope, dynamically recalculated from current portfolio value.

**Interface-agnostic engine.** The engine never prints, never serves HTTP, never knows how it's being observed. It runs, writes to the store, and dispatches events to listeners. A CLI dashboard, a FastAPI server, a Telegram bot — all are just different listeners wired to the same engine.

**Database is the single source of truth for everything except secrets.** Settings, targets, positions, trades — all in SQLite with WAL mode. The engine reads config from the database each tick. External tools (CLI subcommands, future web UI) write to the database. No signaling, no IPC, no file watching. The database is the communication channel.

**Data flows in one direction:**

```
Poll targets → Detect changes → Aggregate (per-target) → Size (allocation-aware) → Execute → Persist
```

### File Architecture

```
prediction_mirror/
│
├── __init__.py
├── __main__.py                            CLI entry (click)
│
├── models/                                ── Domain data types (no logic, just shapes) ──
│   ├── __init__.py                        Re-exports all models for clean imports
│   ├── market.py                          Market, MarketStatus
│   ├── position.py                        TargetPosition, OurPosition
│   ├── signal.py                          Signal, SignalType (BUY/SELL)
│   ├── order.py                           SizedOrder, OrderResult, OrderSide
│   ├── wallet.py                          WalletState
│   ├── target.py                          TargetConfig (address, allocation %, platform, label)
│   └── settings.py                        Settings dataclass (typed, with defaults)
│
├── platforms/                             ── Platform adapters (the outside world) ──
│   ├── __init__.py                        Registry: get_adapter_class(name) → class
│   ├── base.py                            Abstract PlatformAdapter (ABC)
│   ├── errors.py                          PlatformError, TransientError, FatalError
│   └── polymarket/                        ── Polymarket-specific implementation ──
│       ├── __init__.py
│       ├── config.py                      Constants + secret loading from POLYMARKET_* env vars
│       ├── adapter.py                     PolymarketAdapter (wraps pmxt for trading)
│       ├── data_api.py                    Data API: target positions + market resolution status
│       └── blockchain.py                  Web3: gas balance, approvals, redemption
│
├── engine/                                ── Core logic (platform-agnostic) ──
│   ├── __init__.py
│   ├── core.py                            Engine class: lifecycle, loops, listener dispatch
│   ├── listener.py                        EngineListener protocol definition
│   ├── monitor.py                         Poll loop, position diffing, signal generation
│   ├── strategy.py                        Allocation-aware sizing, per-target multipliers
│   ├── executor.py                        Per-target aggregation, submission, retries, dry-run
│   └── redeemer.py                        Periodic resolved-market redemption + dry-run P&L
│
├── store/                                 ── SQLite persistence (single source of truth) ──
│   ├── __init__.py                        Store facade class
│   ├── database.py                        Connection management, schema init, WAL mode
│   ├── settings.py                        Settings CRUD + typed Settings dataclass coercion
│   ├── targets.py                         Targets CRUD + allocation validation
│   ├── snapshots.py                       Target position snapshot queries (for diffing)
│   ├── signals.py                         Signal audit log queries
│   ├── trades.py                          Executed trade record queries
│   └── portfolio.py                       Our positions + per-target allocation tracking
│
├── dashboard/                             ── CLI status display (rich, implements EngineListener) ──
│   ├── __init__.py
│   ├── listener.py                        DashboardListener: receives engine events, triggers renders
│   ├── renderer.py                        rich.live.Live dashboard rendering
│   ├── portfolio_view.py                  Positions, P&L, per-target allocation (rich.table)
│   └── activity_view.py                   Recent signals, trades, errors (rich.table)
│
└── utils/                                 ── Shared pure utilities ──
    ├── __init__.py
    ├── log.py                             Structured logging (console + rotating file)
    ├── formatting.py                      USD formatting, address shortening, timestamps
    └── conversions.py                     Currency decimal handling, unit math
```

**30 files across 7 directories.**

### Dependency Graph

```
models/                  ← used by everyone (shared types)
utils/                   ← used by platforms/, engine/, dashboard/

platforms/base           ← defines the adapter interface
platforms/errors         ← error taxonomy used by adapter + engine
platforms/polymarket/    ← implements the interface (wraps pmxt + httpx + web3.py)
  └── config.py          ← hardcoded constants + reads POLYMARKET_* env vars

store/database           ← used by all store modules
store/settings           ← read by engine (every tick), written by CLI
store/targets            ← read by engine (every tick), written by CLI
store/*                  ← used by engine/, dashboard/

engine/listener          ← defines the observer protocol
engine/core              ← orchestrates loops, reads store/settings + store/targets each tick
engine/monitor           ← uses PlatformAdapter (interface), store/snapshots
engine/strategy          ← uses models only (pure logic, no I/O)
engine/executor          ← uses strategy, PlatformAdapter (interface), store/
engine/redeemer          ← uses PlatformAdapter (interface), store/portfolio

dashboard/listener       ← implements EngineListener, reads store
dashboard/renderer       ← uses rich.live.Live, composes views
dashboard/*_view         ← pure formatting functions (rich.table.Table)

__main__                 ← wires everything, routes subcommands (click)
```

**No circular dependencies. The engine is unaware of its interface. The store is the sole communication channel between all components.**

---

## Models

All dataclasses. No logic, no methods beyond `__post_init__` validation. Shared contracts between every module.

### `models/target.py`
```
TargetConfig:
  label: str                        Human-readable name (unique identifier)
  platform: str                     "polymarket", "kalshi", etc.
  address: str                      Wallet address or account ID
  allocation_pct: float             % of total portfolio budget (e.g. 50.0)
  multiplier: float                 Per-target sizing multiplier (default 1.0)
  enabled: bool                     Active or paused
```

### `models/market.py`
```
MarketStatus (enum): OPEN, RESOLVED, CLOSED

Market:
  market_id: str                    Platform's market identifier (conditionId for Polymarket)
  platform: str
  question: str                     Human-readable market question
  outcomes: list[str]               ["Yes", "No"] or similar
  status: MarketStatus
  resolution_outcome: str | None    Which outcome won (if resolved)
```

Note: For Polymarket, `market_id` is the `conditionId` from the Data API. The adapter maps
`MarketOutcome.outcome_id` → `asset_id` and `MarketOutcome.label` → `outcome` at query time.
No asset_id mapping needed on the Market model itself.

### `models/position.py`
```
TargetPosition:
  target_address: str
  platform: str
  market_id: str
  asset_id: str                     Token ID / contract ID
  outcome: str                      "Yes" / "No"
  size: float                       Number of contracts/shares held
  avg_price: float                  From Data API (server-calculated)
  current_price: float
  snapshot_time: datetime

OurPosition:
  market_id: str
  asset_id: str
  platform: str
  outcome: str
  size: float
  avg_entry_price: float
  total_cost: float                 Total USD deployed in this position
  realized_pnl: float              Accumulated realized P&L (default 0)
  source_target: str                Which target's label triggered this
  dry_run: bool                     Whether this is a paper position
  updated_at: datetime
```

Position update logic:
- Buy fill: `total_cost += fill_size * fill_price`, `size += fill_size`, `avg_entry = total_cost / size`
- Sell fill: `size -= fill_size`, `total_cost = size * avg_entry_price` (avg unchanged)

### `models/signal.py`
```
SignalType (enum): BUY, SELL

Signal:
  signal_type: SignalType
  target: TargetConfig              Full target reference (in-memory only, carries allocation info)
  platform: str
  market_id: str
  asset_id: str
  outcome: str
  target_delta: float               How many shares the target moved
  target_prev_size: float           Target's holding before this change (for sell % calc)
  target_price: float               Price at time of detection
  detected_at: datetime
```

Note: Signal carries full `TargetConfig` in memory for the engine pipeline. The `signals` DB table
only stores `target_address` and `target_label`. DB signal queries return rows for display only,
not `Signal` objects. No round-tripping needed.

### `models/order.py`
```
OrderSide (enum): BUY, SELL

SizedOrder:
  signal: Signal
  side: OrderSide
  asset_id: str
  price: float
  size: float                       Our calculated size (shares)
  usd_amount: float                 Dollar value of the order
  dry_run: bool

OrderResult:
  order: SizedOrder
  success: bool
  order_id: str | None
  fill_price: float | None
  fill_size: float | None
  error: str | None
  executed_at: datetime
```

Note: `signal_id` is NOT embedded in OrderResult. The executor threads it as a local variable:
`signal_id = store.signals.insert_signal(signal)` → `store.trades.insert_trade(result, signal_id)`.

### `models/wallet.py`
```
WalletState:
  platform: str
  total_balance: float              Available for trading (USD/USDC)
  gas_balance: float | None         Native gas token (None for centralized platforms)
  approvals_ok: bool                Whether required approvals are in place
```

### `models/settings.py`
```
Settings:
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

Constructed by `store/settings.py:get_current()` which reads key-value strings from SQLite
and casts to proper types. All coercion happens there and nowhere else.

---

## Platform Adapters

### `platforms/errors.py` — Error Taxonomy

```python
class PlatformError(Exception):
    """Base for all platform adapter errors."""

class TransientError(PlatformError):
    """Retryable: network timeout, 429 rate limit, 5xx server error."""

class FatalError(PlatformError):
    """Not retryable: invalid order, insufficient funds, auth failure, 4xx."""
```

The adapter wraps pmxt exceptions and httpx errors into these categories.
The executor retries on `TransientError`, logs and skips on `FatalError`.

### `platforms/base.py` — Abstract Adapter

The contract every platform fulfills. The engine only talks to this interface.

```python
class PlatformAdapter(ABC):

    # ── Lifecycle ──

    @abstractmethod
    async def initialize(self) -> None:
        """One-time setup: authenticate, set approvals, warm caches."""

    async def shutdown(self) -> None:
        """Clean up connections. Default no-op."""

    # ── Factory ──

    @classmethod
    @abstractmethod
    def from_env(cls) -> "PlatformAdapter":
        """Construct from platform-specific env vars.
        Regular __init__ takes explicit params (for testing)."""

    # ── Read: Targets ──

    @abstractmethod
    async def fetch_target_positions(self, address: str) -> list[TargetPosition]: ...

    @abstractmethod
    async def fetch_target_portfolio_value(self, address: str) -> float: ...

    # ── Read: Markets ──

    @abstractmethod
    async def fetch_market(self, market_id: str) -> Market: ...

    @abstractmethod
    async def get_price(self, asset_id: str, side: str) -> float:
        """Get current price. side is 'buy' (best ask) or 'sell' (best bid)."""

    # ── Read: Our Wallet ──

    @abstractmethod
    async def get_wallet_state(self) -> WalletState: ...

    # ── Write: Trading ──

    @abstractmethod
    async def submit_order(self, order: SizedOrder) -> OrderResult: ...

    async def cancel_order(self, order_id: str) -> bool:
        return False

    async def redeem_if_needed(self, market_id: str, position: OurPosition) -> bool:
        return True  # Default no-op for auto-redeeming platforms

    # ── Metadata ──

    @property
    @abstractmethod
    def platform_name(self) -> str: ...

    @property
    @abstractmethod
    def currency_decimals(self) -> int: ...
```

### `platforms/__init__.py` — Adapter Registry

```python
_REGISTRY: dict[str, type[PlatformAdapter]] = {}

def register_adapter(name: str, cls: type[PlatformAdapter]):
    _REGISTRY[name] = cls

def get_adapter_class(platform_name: str) -> type[PlatformAdapter]:
    """Returns the adapter CLASS. Caller instantiates via cls.from_env()."""
    return _REGISTRY[platform_name]
```

### `platforms/polymarket/`

**`config.py`** — Hardcoded public constants (Data API URL, contract addresses, chain ID 137).
Loads `POLYMARKET_PRIVATE_KEY` and `POLYMARKET_RPC_URL` from environment. Validates on construction.

**`adapter.py`** — `PolymarketAdapter` implements `PlatformAdapter`. Wraps `pmxt.Polymarket` for
trading operations. Uses `asyncio.to_thread()` for all sync pmxt calls. Composes `data_api` and
`blockchain` for target monitoring and chain ops.

**`data_api.py`** — `httpx.AsyncClient` for:
- `GET https://data-api.polymarket.com/positions?user={addr}` — target positions
- Market resolution status checking
- Maps Data API response fields to `TargetPosition` models

**`blockchain.py`** — `web3.py` for:
- MATIC balance check (gas health)
- USDC + CTF token approvals
- `redeemPositions()` on ConditionalTokens contract

---

## Engine

### `engine/listener.py` — Event Protocol

```python
class EngineListener(Protocol):
    def on_signal(self, signal: Signal) -> None: ...
    def on_trade(self, result: OrderResult) -> None: ...
    def on_position_update(self, position: OurPosition) -> None: ...
    def on_redeemed(self, position: OurPosition, pnl: float) -> None: ...
    def on_error(self, error: str, context: dict) -> None: ...
    def on_status_change(self, status: str, detail: str) -> None: ...
```

All methods are optional no-ops by default. Multiple listeners can be registered.
Listeners are sync — async listeners can queue events internally.

### `engine/core.py` — Engine Orchestrator

The central runtime. Reads settings and targets from the store on each tick — no config is held as mutable state, no update methods needed.

```
class Engine:
    __init__(store: Store, adapters: dict[str, PlatformAdapter])

    # ── Listener management ──
    add_listener(listener: EngineListener)
    remove_listener(listener: EngineListener)
    _dispatch(event_name: str, *args)

    # ── Runtime ──
    async run()           Starts all loops, blocks until shutdown
    async shutdown()      Cancel tasks, flush, cleanup

    # ── Internal loops ──
    _monitor_loop()
        Each tick:
          settings = store.settings.get_current()
          targets = store.targets.get_enabled()
          for target in targets:
              try:
                  signals = monitor.poll_target(target, adapter)
                  if signals:
                      executor.handle_signals(signals, adapter, store, settings)
              except TransientError as e:
                  _dispatch("on_error", str(e), {"target": target.label, "transient": True})
              except Exception as e:
                  _dispatch("on_error", str(e), {"target": target.label, "transient": False})
                  logger.exception(f"Error polling target {target.label}")
          await asyncio.sleep(settings.poll_interval_seconds)

    _redeemer_loop()
        Each tick:
          settings = store.settings.get_current()
          redeemer.check_and_redeem(adapters, store)
          await asyncio.sleep(settings.redeemer_interval_seconds)
```

Key: **per-target try/except — the loop never crashes.** Log the error, dispatch to listeners, continue to next target.

**Config changes propagate automatically.** CLI writes to DB → engine reads from DB next tick. No signaling, no IPC.

### Startup Sequence

```
1.  load_dotenv()
2.  Parse CLI args (click)
3.  Resolve DB path (--db flag > PMT_DB_PATH env > ./prediction_mirror.db)
4.  init_db(path) → creates tables, seeds defaults, enables WAL
5.  For each platform in enabled targets:
      adapter = get_adapter_class(platform).from_env()
      await adapter.initialize()  # pmxt server starts, checks approvals
6.  engine = Engine(store, adapters)
7.  dashboard = DashboardListener(store)
8.  engine.add_listener(dashboard)
9.  Register SIGINT/SIGTERM handler → engine.shutdown()
10. await engine.run()  # blocks until shutdown
11. store.close()
```

### Graceful Shutdown

```python
async def shutdown(self):
    self._running = False
    for task in self._tasks:
        task.cancel()
    await asyncio.gather(*self._tasks, return_exceptions=True)
    for adapter in self._adapters.values():
        await adapter.shutdown()
    self._dispatch("on_status_change", "stopped", "Shutdown complete")
```

SIGINT/SIGTERM registered via `asyncio.get_event_loop().add_signal_handler()`.

### `engine/monitor.py` — Detection

```
poll_target(target, adapter, store) → list[Signal]
diff_positions(old, new, target) → list[Signal]        (pure function)

Diff logic:
  NOT in old           → BUY signal (target_prev_size = 0)
  size increased       → BUY signal (delta = new - old, target_prev_size = old)
  size decreased       → SELL signal (delta = old - new, target_prev_size = old)
  size reached zero    → SELL signal (full exit, target_prev_size = old)
  Noise filter: skip deltas below dust threshold.
  After diff: upsert snapshot into store.

  Monitor populates target_prev_size on every signal — it has both old and
  new snapshots during diffing. Strategy uses this for sell percentage calculation.
```

Sequential polling for MVP. With 2-5 targets and ~200ms per API call, each poll cycle takes <1s.

### `engine/strategy.py` — Allocation-Aware Sizing

Pure calculation. No I/O, no side effects, no platform awareness. Buy and sell use fundamentally different algorithms.

```
size_order(signal, portfolio_value, target_portfolio_value,
           deployed_for_target, our_position, settings) → SizedOrder | None

BUY algorithm — scale target's delta relative to our budget:
  1.  target_budget     = portfolio_value × (target.allocation_pct / 100)
  2.  available         = target_budget - deployed_for_target
  3.  If available ≤ 0  → return None
  4.  ratio             = target_budget / target_portfolio_value
  5.  raw_size          = signal.target_delta × ratio × target.multiplier
  6.  usd_amount        = raw_size × current_price
  7.  Cap at available budget
  8.  Cap at settings.max_order_usd
  9.  Cap at settings.max_position_usd (considering existing holding)
  10. Skip if below settings.min_order_usd → return None
  11. Slippage check → return None if exceeded
  12. Return SizedOrder

SELL algorithm — mirror target's percentage reduction on our position:
  1.  If our_position is None or size ≤ 0 → return None (nothing to sell)
  2.  If target exited entirely (target_prev_size - delta ≈ 0) → sell 100% of our position
  3.  reduction_pct    = abs(signal.target_delta) / signal.target_prev_size
  4.  raw_size         = our_position.size × reduction_pct
  5.  usd_amount       = raw_size × current_price
  6.  Cap at our actual holding
  7.  Skip if below settings.min_order_usd → return None
  8.  Slippage check → return None if exceeded
  9.  Return SizedOrder

Why sells differ from buys:
  Buy sizing answers: "How much should we spend proportional to our budget?"
  Sell sizing answers: "The target reduced conviction by X%, so we reduce by X%."
  Using budget-ratio for sells breaks when our position has drifted from
  partial fills, timing, or price changes. Percentage-based selling correctly
  tracks the target's intent regardless of position drift.
```

Portfolio value = liquid_balance + sum(all real deployed positions at current market value).
Dry-run positions excluded from portfolio value (paper trading uses budget based on actual capital).
Allocation is dynamic: "20%" means 20% of current portfolio value, recalculated each time.

#### Slippage Check

```python
def check_slippage(signal_price: float, current_price: float, tolerance_pct: float) -> bool:
    """Returns True if slippage is acceptable."""
    if signal_price <= 0:
        return True  # No reference price
    slippage_pct = abs(current_price - signal_price) / signal_price * 100
    return slippage_pct <= tolerance_pct
```

- `signal_price` = price when the signal was detected
- `current_price` = price at order time from `adapter.get_price(asset_id, side)`
- `tolerance_pct` = `settings.slippage_tolerance_pct` (default 2.0%)

### `engine/executor.py` — Execution Pipeline

```
handle_signals(signals, adapters, store, settings)
aggregate_signals(signals, store) → list[Signal]
execute_order(sized_order, adapter) → OrderResult
retry_order(order, adapter, attempts=3) → OrderResult

Aggregation: per-target, NOT per-market.
  Two targets entering the same market → two separate orders.
  aggregation_window_seconds = 0 for MVP (pass-through, reserved for future use).

Execution flow per signal:
  1. Get wallet state, target portfolio value, deployed capital, existing position
  2. Calculate portfolio_value (liquid + all real deployed)
  3. strategy.size_order() → SizedOrder or None
  4. If dry_run → log + persist as paper trade/position
  5. Else → submit via adapter, retry on transient failure
  6. Persist result atomically (with conn: insert trade + update position)
  7. Dispatch to listeners

Retry policy:
  - Max attempts: 3
  - Backoff: exponential (1s, 2s, 4s)
  - Retryable: TransientError (network, 429, 5xx)
  - Fatal (no retry): FatalError (4xx except 429, invalid params, insufficient funds)
  - Timeout per attempt: 10 seconds
```

### `engine/redeemer.py` — Redemption + Dry-Run P&L

```
run_redeemer_pass(adapters, store)
redeem_position(adapter, position, market) → (bool, float)
calculate_dry_run_pnl(position, market) → float

For resolved markets:
  Real positions → adapter.redeem_if_needed()
  Dry-run positions → calculate hypothetical P&L:
    Outcome matches resolution → profit = size × (1.0 - avg_entry_price)
    Outcome doesn't match      → loss   = size × avg_entry_price (negative)
  Update realized_pnl, zero out position, record as REDEEM trade, dispatch on_redeemed.
```

---

## Store

### `store/__init__.py` — Store Facade

```python
class Store:
    """Facade grouping all store modules with a shared connection."""
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
    # Methods delegate to submodules, passing self.conn
```

All callers import: `from prediction_mirror.store import Store`

### `store/database.py` — Connection & Schema

```python
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

Module-level singleton. WAL mode enables concurrent reads (CLI) while the engine writes.
`check_same_thread=False` for asyncio.to_thread() compatibility.

### `store/settings.py` — Settings CRUD

```
DEFAULTS: dict[str, str]          Hardcoded default values (see models/settings.py)

seed_defaults(conn)               INSERT OR IGNORE for each key in DEFAULTS.
                                  Runs every startup. New keys appear automatically.
                                  Existing values are never overwritten.

get_current(conn) → Settings      Reads all key-value strings, casts to typed Settings dataclass.
                                  All type coercion happens here and nowhere else.
get_value(conn, key) → str        Single setting value
set_value(conn, key, value)       Update. Rejects unknown keys.
get_all(conn) → list[tuple]       All key-value pairs (for CLI list command)
```

### `store/targets.py` — Targets CRUD

```
add_target(conn, target: TargetConfig)
    Validates: allocation sum ≤ 100%, no duplicate label/address.

get_enabled(conn) → list[TargetConfig]
get_all(conn) → list[TargetConfig]
get_by_label(conn, label) → TargetConfig | None

update_target(conn, label, **changes)
enable_target(conn, label)
disable_target(conn, label)
remove_target(conn, label)

set_allocation(conn, label, pct)
    Validates: new sum ≤ 100%.

validate_allocations(conn) → bool
    Sum of enabled targets' allocation_pct ≤ 100%.
```

### `store/snapshots.py` — Target State for Diffing

```
upsert_snapshot(conn, target_position)
get_snapshot(conn, target_address, platform, market_id, asset_id) → TargetPosition | None
get_all_snapshots(conn, target_address) → list[TargetPosition]
delete_stale_snapshots(conn, older_than: datetime)
```

### `store/signals.py` — Signal Audit Log

```
insert_signal(conn, signal) → int
get_recent_signals(conn, target_label, minutes) → list[Row]
get_signal_history(conn, since, limit) → list[Row]
```

Returns `sqlite3.Row` objects for display, not `Signal` dataclass instances.

### `store/trades.py` — Execution Records

```
insert_trade(conn, order_result, signal_id)
get_recent_trades(conn, limit) → list[Row]
get_trades_for_target(conn, target_label, since) → list[Row]
get_trade_summary(conn, dry_run: bool | None = None) → dict
```

### `store/portfolio.py` — Positions + Allocation Tracking

```
upsert_position(conn, our_position)
get_position(conn, market_id, asset_id, source_target) → OurPosition | None
get_all_positions(conn, dry_run: bool | None = None) → list[OurPosition]
get_positions_by_target(conn, target_label) → list[OurPosition]
zero_out_position(conn, market_id, asset_id, source_target)

get_deployed_for_target(conn, target_label) → float
get_total_deployed(conn) → float
get_allocation_summary(conn, targets, portfolio_value) → dict[str, dict]
```

### Transaction Boundaries

The executor wraps trade persistence atomically:
```python
with conn:  # sqlite3 context manager = transaction
    trades.insert_trade(conn, result, signal_id)
    portfolio.upsert_position(conn, position_update)
```

### SQLite Schema

```sql
CREATE TABLE IF NOT EXISTS settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS targets (
    label           TEXT PRIMARY KEY,
    platform        TEXT    NOT NULL,
    address         TEXT    NOT NULL,
    allocation_pct  REAL    NOT NULL,
    multiplier      REAL    NOT NULL DEFAULT 1.0,
    enabled         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT    NOT NULL,
    UNIQUE(platform, address)
);

CREATE TABLE IF NOT EXISTS target_snapshots (
    target_address  TEXT    NOT NULL,
    platform        TEXT    NOT NULL,
    market_id       TEXT    NOT NULL,
    asset_id        TEXT    NOT NULL,
    outcome         TEXT    NOT NULL,
    size            REAL    NOT NULL,
    avg_price       REAL,
    current_price   REAL,
    snapshot_time   TEXT    NOT NULL,
    PRIMARY KEY (target_address, platform, market_id, asset_id)
);

CREATE TABLE IF NOT EXISTS signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_type     TEXT    NOT NULL,
    target_address  TEXT    NOT NULL,
    target_label    TEXT    NOT NULL,
    platform        TEXT    NOT NULL,
    market_id       TEXT    NOT NULL,
    asset_id        TEXT    NOT NULL,
    outcome         TEXT    NOT NULL,
    target_delta    REAL    NOT NULL,
    target_prev_size REAL   NOT NULL DEFAULT 0,
    target_price    REAL,
    detected_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS executed_trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id       INTEGER REFERENCES signals(id),
    target_address  TEXT    NOT NULL,
    target_label    TEXT    NOT NULL,
    platform        TEXT    NOT NULL,
    side            TEXT    NOT NULL,
    market_id       TEXT    NOT NULL,
    asset_id        TEXT    NOT NULL,
    ordered_price   REAL    NOT NULL,
    ordered_size    REAL    NOT NULL,
    fill_price      REAL,
    fill_size       REAL,
    usd_amount      REAL,
    order_id        TEXT,
    success         INTEGER NOT NULL,
    dry_run         INTEGER NOT NULL,
    error           TEXT,
    executed_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS our_positions (
    market_id       TEXT    NOT NULL,
    asset_id        TEXT    NOT NULL,
    platform        TEXT    NOT NULL,
    outcome         TEXT    NOT NULL,
    size            REAL    NOT NULL DEFAULT 0,
    avg_entry_price REAL    NOT NULL DEFAULT 0,
    total_cost      REAL    NOT NULL DEFAULT 0,
    realized_pnl    REAL    NOT NULL DEFAULT 0,
    source_target   TEXT    NOT NULL,
    dry_run         INTEGER NOT NULL DEFAULT 0,
    updated_at      TEXT    NOT NULL,
    PRIMARY KEY (market_id, asset_id, source_target)
);

CREATE INDEX IF NOT EXISTS idx_signals_detected  ON signals(detected_at);
CREATE INDEX IF NOT EXISTS idx_signals_target     ON signals(target_label);
CREATE INDEX IF NOT EXISTS idx_trades_executed    ON executed_trades(executed_at);
CREATE INDEX IF NOT EXISTS idx_trades_target      ON executed_trades(target_label);
CREATE INDEX IF NOT EXISTS idx_positions_target   ON our_positions(source_target);
CREATE INDEX IF NOT EXISTS idx_positions_dry_run  ON our_positions(dry_run);
```

---

## Dashboard

Uses `rich` library. Implements `EngineListener`. Receives real-time event pushes from the engine and renders status.

### Layout

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

Rendered via `rich.live.Live` with `rich.table.Table` for each section.
Refreshes every `dashboard_refresh_seconds` (default 30s) or immediately on signal/trade events.

### `dashboard/listener.py`

```
DashboardListener:
  Implements EngineListener protocol.
  Queues updates on events, renders on interval or on_status_change.
```

### `dashboard/renderer.py`

```
render_full_dashboard(store, targets)      → rich.table.Table composition
render_header(uptime, dry_run_mode, target_count)
```

Uses `rich.live.Live` for auto-refresh.

### `dashboard/portfolio_view.py`

```
render_positions_table(positions)          → rich.table.Table
render_allocation_breakdown(allocation_summary)  → rich.table.Table
    Per-target: label | allocation % | budget $ | deployed $ | available $
    Footer: unallocated reserve % and $
render_total_summary(portfolio_value, total_pnl, dry_run_pnl)
```

### `dashboard/activity_view.py`

```
render_recent_signals(signals, n=10)       → rich.table.Table
render_recent_trades(trades, n=10)         → rich.table.Table
render_errors(errors, n=5)                 → rich.table.Table
```

---

## Logging

```python
# utils/log.py
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_FILE = "prediction_mirror.log"
MAX_BYTES = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 3

configure_logging(level: str = "INFO") → None
    Console handler: INFO+ by default
    File handler: DEBUG+, rotating (10MB, 3 backups)

get_logger(name: str) → logging.Logger
    Returns logging.getLogger(f"prediction_mirror.{name}")
```
