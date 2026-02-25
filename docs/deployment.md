# Deployment

## Docker

```bash
# Build
docker build -t prediction-mirror-trader .

# Run
docker compose up -d
```

The bot reads credentials from `.env` and persists its database to a Docker volume.

The Docker image includes Node.js (required by the pmxt sidecar server) and Python 3.12.

## Pre-deployment Setup

Before deploying, configure the bot using the CLI against the database file:

```bash
# Disable dry-run mode
python -m prediction_mirror settings set dry_run false

# Add at least one target
python -m prediction_mirror targets add \
    --label "Target Name" \
    --address "0x..." \
    --platform polymarket \
    --allocation 50
```

See [configuration.md](configuration.md) for all available settings.

## Logging

The bot writes logs to two destinations:

- **Console** — INFO level and above
- **File** — DEBUG level and above, written to `prediction_mirror.log`

Log files rotate automatically at 10 MB with 3 backups kept. Configure the log level via:

```bash
python -m prediction_mirror settings set log_level DEBUG
```

## Database

All state lives in a single SQLite file (default: `./prediction_mirror.db`, configurable via `PMT_DB_PATH` or `--db`).

The database uses WAL mode for safe concurrent reads (CLI commands while the bot is running).

**Backups:** Copy the `.db`, `.db-wal`, and `.db-shm` files together. Or stop the bot first and copy just the `.db` file.

## Monitoring

The bot logs every signal, trade, and error. To check health:

- Watch `prediction_mirror.log` for errors
- Query the database directly: `sqlite3 prediction_mirror.db "SELECT COUNT(*) FROM executed_trades WHERE success=0"`
- The engine dispatches errors to listeners without crashing — a single target failure does not affect others

## Resource Requirements

The bot is lightweight:

- **CPU** — minimal (sleeps between polls)
- **Memory** — ~50-100 MB (Python + Node.js sidecar)
- **Disk** — database grows slowly (signals + trades); log rotation caps at ~40 MB
- **Network** — one HTTP request per target per poll interval (default 2s)
