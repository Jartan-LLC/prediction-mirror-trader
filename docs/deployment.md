# Deployment

## Docker

```bash
# Build
docker build -t prediction-mirror-trader .

# Run
docker compose up -d
```

The bot reads credentials from `.env` and persists its database to a Docker volume.

## Configuration

Before deploying, disable dry-run mode:

```bash
python -m prediction_mirror settings set dry_run false
```

Add at least one target:

```bash
python -m prediction_mirror targets add \
    --label "Target Name" \
    --address "0x..." \
    --platform polymarket \
    --allocation 50
```

See [configuration.md](configuration.md) for all available settings.
