# Phase 2: Stack Research & Decisions

Status: COMPLETE

---

## 2.1 pmxt SDK — The Key Decision

### What pmxt Is

pmxt (v2.14.1, MIT, 697 stars) is "CCXT for prediction markets" — a unified API for Polymarket, Kalshi, Limitless, and others. Source inspected at `/home/vscode/.local/lib/python3.12/site-packages/pmxt/`.

**Architecture:** Python SDK is a thin wrapper around a Node.js sidecar server (267K-line `bundled.js`). The SDK auto-starts the sidecar on first use. All API calls go Python → localhost HTTP → sidecar → exchange APIs.

**Dependencies:** pydantic, python-dateutil, typing-extensions, urllib3. Requires Node.js at runtime.

### What pmxt Provides

| Capability | Method | Notes |
|-----------|--------|-------|
| Market data | `fetch_markets()`, `fetch_market()`, `fetch_order_book()` | Full market metadata + orderbook |
| Our positions | `fetch_positions()` | Returns authenticated user's positions |
| Our balance | `fetch_balance()` | Returns `Balance(currency, total, available, locked)` |
| Order creation | `create_order(outcome_id, side, type, amount, price)` | Handles signing, auth, submission |
| Order management | `cancel_order()`, `fetch_order()`, `fetch_open_orders()` | Full order lifecycle |
| Execution pricing | `get_execution_price(order_book, side, amount)` | VWAP from orderbook |
| Trade history | `fetch_my_trades()`, `fetch_trades()` | User and market trades |
| WebSocket streams | `watch_order_book()`, `watch_trades()`, `watch_user_positions()` | Real-time data |
| Raw API access | `call_api(operation_id, params)` | Escape hatch for any endpoint |
| Multi-exchange | `Polymarket`, `Kalshi`, `KalshiDemo`, `Limitless` | Same interface |

### What pmxt Does NOT Provide

| Gap | Impact | Workaround |
|-----|--------|------------|
| **Target wallet positions** | CRITICAL — `fetch_positions()` only returns OUR positions, takes no address param | Direct HTTP to Data API: `GET https://data-api.polymarket.com/positions?user={address}` |
| **Position redemption** | Needed for resolved markets | Direct web3.py call to ConditionalTokens contract `redeemPositions()` |
| **Gas balance (MATIC)** | Needed for wallet health check | Direct web3.py call `w3.eth.get_balance(address)` |
| **Token approvals** | Needed on first setup | Direct web3.py calls to USDC + ConditionalTokens `approve()` |
| **Async support** | Our engine is asyncio-based | Wrap sync calls with `asyncio.to_thread()` |
| **Market resolution status** | `UnifiedMarket` has no status/resolution fields | Direct HTTP to Gamma API or Data API |

### Critical Finding: fetch_positions() Signature

```python
def fetch_positions(self) -> List[Position]:
    # No address parameter. Only returns authenticated user's positions.
```

This means pmxt handles OUR trading but NOT target monitoring. We need a separate mechanism for polling target wallets.

### pmxt Data Models

```python
Position(market_id, outcome_id, outcome_label, size, entry_price, current_price, unrealized_pnl, realized_pnl)
Balance(currency, total, available, locked)
Order(id, market_id, outcome_id, side, type, amount, status, filled, remaining, timestamp, price, fee)
OrderBook(bids: List[OrderLevel], asks: List[OrderLevel], timestamp)
UnifiedMarket(market_id, title, outcomes: List[MarketOutcome], volume_24h, liquidity, url, ...)
MarketOutcome(outcome_id, label, price, price_change_24h, metadata, market_id)
```

### Decision: Use pmxt as Primary SDK

**Yes — use pmxt for our trading operations. Supplement with direct API calls for monitoring and blockchain ops.**

**Rationale:**
1. Handles the hardest parts automatically (CLOB auth, EIP-712 signing, order creation)
2. Multi-exchange support aligns perfectly with our platform-agnostic architecture
3. `call_api()` escape hatch available for raw endpoint access
4. Active project (83 releases, 10 contributors, last release Feb 2026)
5. We avoid reimplementing CLOB auth/signing — that's ~500 lines of fiddly cryptographic code
6. Adding Kalshi/Limitless later becomes trivial (same interface)

**What we still build ourselves:**
- Target wallet position monitoring (Data API HTTP, ~50 lines)
- Market resolution status checking (Gamma API HTTP, ~30 lines)
- Blockchain ops: redemption, approvals, gas check (web3.py, ~100 lines)
- `asyncio.to_thread()` wrappers for pmxt sync calls

### Architecture Impact

The `platforms/polymarket/` directory changes from the original 5-file plan:

| Original Plan | With pmxt |
|---------------|-----------|
| `config.py` — constants + env vars | `config.py` — simplified, pmxt handles most auth |
| `adapter.py` — implements PlatformAdapter | `adapter.py` — wraps pmxt.Polymarket behind PlatformAdapter |
| `positions_api.py` — Gamma API for target positions | `data_api.py` — Data API HTTP for target positions + market resolution |
| `orderbook.py` — CLOB price/signing/orders | REMOVED — pmxt handles this |
| `blockchain.py` — web3 balances/approvals/redemption | `blockchain.py` — SIMPLIFIED, only redemption + gas + approvals |

**Renamed `positions_api.py` → `data_api.py`** because it now hits the Data API (not Gamma) for target positions.

### Docker Impact

The Dockerfile needs Node.js in addition to Python:
```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y nodejs npm && rm -rf /var/lib/apt/lists/*
```

Or use a multi-runtime base image.

---

## 2.2 HTTP Client for Direct API Calls

We need an HTTP client for the supplementary API calls (Data API for target positions, Gamma API for market resolution). pmxt handles CLOB internally.

### Options

| Library | Async | Test Mocking | Dependencies |
|---------|-------|-------------|-------------|
| `aiohttp` | native | `aioresponses` | Large C extension |
| `httpx` | native (`httpx[asyncio]`) | `respx` | Pure Python, requests-like API |
| `urllib3` | no | — | Already installed (pmxt dep) |

### Decision: httpx

**Rationale:**
1. Native async support (`httpx.AsyncClient`)
2. `respx` for test mocking is clean and well-maintained
3. Already installed as a transitive dependency (py-clob-client pulls it in)
4. requests-compatible API (familiar)
5. Lighter than aiohttp (no C extensions)

---

## 2.3 EIP-712 Signing

### Decision: Handled by pmxt

pmxt's sidecar server handles all EIP-712 order signing internally. We do not need `py-order-utils` or manual signing for trade orders.

For the CLOB API key derivation (one-time auth setup), pmxt handles this via `init_auth()` on the Polymarket class.

**The only remaining signing need is for blockchain transactions** (approvals, redemption), which web3.py's `eth_account` handles natively.

---

## 2.4 CLI Framework

### Options

| Framework | Dependency | Features |
|-----------|-----------|----------|
| `argparse` (stdlib) | None | Functional but verbose |
| `click` | 1 package | Decorators, auto-help, type validation |
| `typer` | 2 packages (click + typer) | click + type hints |

### Decision: click

**Rationale:**
1. Our CLI surface is moderate (3 command groups, ~10 subcommands)
2. `click` gives us composable command groups, automatic help text, parameter validation
3. Single dependency, widely used, stable
4. `argparse` would work but produces more boilerplate for nested subcommands
5. `typer` adds unnecessary dependency on click anyway plus its own

---

## 2.5 CLI Output Formatting

### Options

| Library | Scope | Weight |
|---------|-------|--------|
| `rich` | Full terminal rendering (tables, colors, live display, progress) | Heavy |
| `tabulate` | Tables only | Lightweight |
| Manual | `str.format()` or f-strings | Zero dependency |

### Decision: rich

**Rationale:**
1. Handles BOTH CLI tables AND the dashboard display
2. `rich.table.Table` for `targets list`, `settings list`
3. `rich.live.Live` for the dashboard refresh loop (replaces manual ANSI clear/print)
4. `rich.console.Console` for colored output, dry-run indicators
5. Widely used (50K+ stars), well-maintained
6. Eliminates the need to implement terminal handling manually
7. The dashboard was the most underspecified part of the design — `rich` gives us a good rendering framework without designing a custom one

---

## 2.6 Settings Type Safety

### Decision: Dataclass with coercion in `get_current()`

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

`store/settings.py:get_current()` reads all key-value strings from SQLite and constructs a `Settings` dataclass with proper type coercion. All callers receive typed fields.

**Rationale:** Explicit types, IDE autocomplete, catches typos at the calling site. No pydantic dependency needed (plain dataclass suffices since we control all inputs).

---

## 2.7 Async DB Access

### Decision: Sync sqlite3 (stdlib)

**Rationale:**
1. The bot has low DB write volume (a few trades per minute max)
2. SQLite writes take <1ms for our data sizes
3. With a 2-second poll interval, blocking for <1ms is negligible
4. `aiosqlite` adds complexity and a dependency for no measurable benefit
5. WAL mode enables concurrent reads from CLI while engine writes

**WAL mode:** Enable on connection init:
```python
conn.execute("PRAGMA journal_mode=WAL")
```

---

## 2.8 Test Mocking Strategy

### Decision: respx + unittest.mock

| What to mock | Tool |
|-------------|------|
| httpx HTTP calls (Data API) | `respx` |
| pmxt SDK calls | `unittest.mock.patch` / `unittest.mock.MagicMock` |
| web3.py blockchain calls | `unittest.mock.patch` |
| SQLite | In-memory DB (`:memory:`) — real SQLite, no mock |

**Rationale:** We mock at the SDK boundary (pmxt calls), not at the HTTP level for pmxt (the sidecar is pmxt's concern). For our direct HTTP calls (Data API via httpx), we use `respx` which integrates natively with `httpx.AsyncClient`.

---

## 2.9 Polymarket API Details (Phase 3 Preview)

### Base URLs

| Service | URL | Auth |
|---------|-----|------|
| CLOB API | `https://clob.polymarket.com` | HMAC headers for trading, none for reads |
| Gamma API | `https://gamma-api.polymarket.com` | None (public) |
| Data API | `https://data-api.polymarket.com` | None (public) |

### Target Position Monitoring — Data API

```
GET https://data-api.polymarket.com/positions?user={address}&sizeThreshold=0
```

Response fields we need:
- `asset` → maps to our `asset_id`
- `conditionId` → maps to our `market_id`
- `size` → position size
- `avgPrice` → average entry price
- `curPrice` → current market price
- `outcome` → "Yes" / "No"
- `outcomeIndex` → 0 or 1
- `title` → market question
- `redeemable` → useful for redeemer

Rate limit: 150 req/10s (Data API positions endpoint).

### Contract Addresses (Polygon, Chain ID 137)

| Contract | Address |
|----------|---------|
| CTF Exchange | `0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E` |
| Neg Risk CTF Exchange | `0xC5d563A36AE78145C45a50134d48A1215220f80a` |
| Conditional Tokens (ERC-1155) | `0x4D97DCd97eC945f40cF65F87097ACe5EA0476045` |
| USDC.e | `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174` |
| Neg Risk Adapter | `0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296` |

### Redemption

On-chain call to ConditionalTokens contract:
```
redeemPositions(collateralToken, parentCollectionId, conditionId, indexSets)
```
- `collateralToken`: USDC.e address
- `parentCollectionId`: `bytes32(0)` (all zeros)
- `conditionId`: from Data API position response
- `indexSets`: `[1, 2]` to redeem both outcomes

Burns entire token balance for the condition (no amount parameter).

### Rate Limits Summary

| Endpoint | Limit |
|----------|-------|
| CLOB general | 9,000/10s |
| CLOB order book/price | 1,500/10s |
| CLOB post order | 3,500/10s burst, 36,000/10min |
| Gamma general | 4,000/10s |
| Data positions | 150/10s |
| Data general | 1,000/10s |

With 10 targets at 2s poll interval = 5 req/s = 50/10s — well within Data API limits.

### CLOB Authentication

1. Derive API creds: sign EIP-712 message → `POST /auth/api-key` → returns `(apiKey, secret, passphrase)`
2. All trading requests include 5 headers: `POLY_ADDRESS`, `POLY_API_KEY`, `POLY_PASSPHRASE`, `POLY_TIMESTAMP`, `POLY_SIGNATURE` (HMAC-SHA256)
3. Orders additionally require EIP-712 signature in the order body
4. **All of this is handled by pmxt internally**

---

## Runtime Dependency List

```toml
[project]
dependencies = [
    "pmxt>=2.14",             # Unified prediction market SDK
    "httpx>=0.27",            # Async HTTP for Data API + Gamma API
    "web3>=6.0",              # Blockchain: redemption, approvals, gas
    "python-dotenv>=1.0",     # .env file loading
    "click>=8.0",             # CLI framework
    "rich>=13.0",             # Terminal tables + dashboard rendering
]
```

Note: `py-clob-client` and `py-order-utils` are NOT needed — pmxt handles signing/trading.

---

## Summary of All Decisions

| Decision | Choice | Key Reason |
|----------|--------|------------|
| Polymarket SDK | **pmxt** (primary) + direct API calls | Handles signing/auth/orders; multi-exchange |
| Target monitoring | **httpx → Data API** | pmxt can't fetch other users' positions |
| Blockchain ops | **web3.py** (direct) | Redemption, approvals, gas — pmxt doesn't cover |
| HTTP client | **httpx** | Async, already installed, respx for testing |
| EIP-712 signing | **pmxt** (handled internally) | No manual signing needed |
| CLI framework | **click** | Clean subcommand groups, low overhead |
| CLI/dashboard output | **rich** | Tables + live dashboard + colors |
| Settings type | **Dataclass** | Typed, IDE-friendly, zero dependency |
| DB driver | **sqlite3** (stdlib, sync) | Low volume, WAL for concurrency |
| DB concurrency | **WAL mode** | CLI + engine can access simultaneously |
| Test HTTP mocking | **respx** | Native httpx integration |
| Test SDK mocking | **unittest.mock** | Mock pmxt at the boundary |
