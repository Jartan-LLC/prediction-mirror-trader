# Configuration

Three categories, clearly separated by what they are.

## Secrets (`.env`)

Credentials that must never be stored in the database. Loaded via `load_dotenv()` on startup. Each platform reads its own prefixed variables.

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
| `poll_interval_seconds` | `2` | How often to check targets |
| `slippage_tolerance_pct` | `2.0` | Max acceptable slippage |
| `min_order_usd` | `1.0` | Orders below this are skipped |
| `max_order_usd` | `500.0` | Per-order cap |
| `max_position_usd` | `1000.0` | Per-position cap |
| `aggregation_window_seconds` | `0` | Signal aggregation window |
| `redeemer_interval_seconds` | `7200` | How often to check for redemptions |
| `dashboard_refresh_seconds` | `30` | Dashboard refresh rate |
| `dry_run` | `true` | Paper trading mode |
| `log_level` | `INFO` | Logging verbosity |

Managed via CLI: `python -m prediction_mirror settings set dry_run false`

## Targets (SQLite `targets` table)

User-managed via CLI. Table starts empty — no seed file or templates.

Each target has: label (unique), platform, address, allocation percentage, multiplier (default 1.0), and enabled status.

Managed via CLI: `python -m prediction_mirror targets add --label "Whale Alpha" --address "0x..." --platform polymarket --allocation 50`

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
