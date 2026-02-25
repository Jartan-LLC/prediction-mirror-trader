# Configuration

## Secrets (`.env`)

Credentials loaded via `load_dotenv()` on startup. Never stored in the database.

```
POLYMARKET_PRIVATE_KEY=abc123...
POLYMARKET_RPC_URL=https://polygon-mainnet.infura.io/v3/YOUR_KEY

# Optional: custom database location (default: ./prediction_mirror.db)
PMT_DB_PATH=/var/data/mirror.db
```

## Settings (SQLite `settings` table)

Key-value pairs with hardcoded defaults. On every startup, `INSERT OR IGNORE` seeds new defaults without overwriting existing values.

| Key | Default | Description |
|-----|---------|-------------|
| `poll_interval_seconds` | `2` | How often to check for new activity |
| `slippage_tolerance_pct` | `2.0` | Max acceptable price slippage (%) |
| `min_order_usd` | `1.0` | Orders below this USD value are skipped |
| `max_order_usd` | `500.0` | Per-order USD cap |
| `max_position_usd` | `1000.0` | Per-position USD cap |
| `redeemer_interval_seconds` | `7200` | How often to check for resolved markets |
| `dashboard_refresh_seconds` | `30` | Dashboard refresh rate (also updates mark-to-market prices) |
| `dry_run` | `true` | Paper trading mode |
| `dry_run_balance_usd` | `1000.0` | Simulated starting balance for paper trading |
| `dry_run_cash` | `-1` | Current simulated cash (auto-managed, don't set manually) |
| `log_level` | `INFO` | Logging verbosity |

Managed via CLI: `python -m prediction_mirror settings set dry_run false`

## Targets (SQLite `targets` table)

Each target has core fields and conviction sizing configuration:

| Field | Default | Description |
|-------|---------|-------------|
| `label` | (required) | Human-readable unique name |
| `platform` | (required) | Platform name (e.g. `polymarket`) |
| `address` | (required) | Wallet address to mirror |
| `allocation_pct` | (required) | Percentage of total portfolio budget |
| `multiplier` | `1.0` | Sizing multiplier applied to all trades |
| `enabled` | `true` | Whether the target is actively polled |
| `sizing_mode` | `conviction` | `conviction` or `proportional` |
| `trade_size_pct` | `1.0` | Base trade size as % of available budget |
| `aggregation_seconds` | `7` | Seconds to batch trade signals before executing |
| `history_window` | `50` | Number of recent trades for conviction percentile |
| `min_history` | `10` | Trades needed before conviction sizing activates (minimum 10) |
| `cold_start_pct` | `0.0` | Budget % per trade during cold start (0 = observe only) |

### Conviction Sizing

The default sizing mode. Each buy trade's USD value is compared against the target's recent trade history to determine conviction level:

- **Low conviction** (small trade for this target): deploy `trade_size_pct` of available budget
- **High conviction** (large trade for this target): deploy up to `2 × trade_size_pct`
- Formula: `available × trade_size_pct × (1 + percentile_rank) × multiplier`

Historical trade data is seeded from the Polymarket activity API on first startup.

### Sell Sizing

Sells mirror the target's percentage reduction. If the target sells 30% of a position, we sell 30% of ours. The target's current position is fetched at sell time for accurate calculation.

Managed via CLI: `python -m prediction_mirror targets add --label "Whale" --address "0x..." --platform polymarket --allocation 50`

## Database Path

Three tiers of precedence:
1. **Default:** `./prediction_mirror.db`
2. **Env var:** `PMT_DB_PATH` in `.env` or shell
3. **CLI flag:** `--db PATH` on any subcommand

## Live Configuration

Config changes propagate without restart. The engine reads settings and targets from the database on each tick.

| Change | How | Picked Up |
|--------|-----|-----------|
| Setting value | `settings set KEY VALUE` | Next tick |
| Target added | `targets add ...` | Next tick |
| Target disabled | `targets disable LABEL` | Next tick |
| Allocation changed | `targets set-allocation LABEL PCT` | Next sizing |
| Secrets changed | Edit `.env`, restart bot | Startup |
