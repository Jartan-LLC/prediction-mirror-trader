# CLI Reference

All subcommands accept `--db PATH` (default: `PMT_DB_PATH` env var, or `./prediction_mirror.db`).

## Bot Control

```
python -m prediction_mirror run [--db PATH] [--no-dashboard]
```

Start the bot. Creates the database and seeds default settings on first run.

`--no-dashboard` disables the live Rich dashboard and outputs scrolling log lines instead. Also auto-detected when stdout is not a TTY (e.g. piped to a file).

## Settings Management

```
python -m prediction_mirror settings list [--db PATH]
```
Display all settings with current values.

```
python -m prediction_mirror settings set KEY VALUE [--db PATH]
```
Update a setting. Validates that the key exists and value type is correct. The running engine picks up the change on its next tick.

## Target Management

```
python -m prediction_mirror targets list [--db PATH]
```
Display all targets with allocation, sizing configuration, and enabled status.

```
python -m prediction_mirror targets add [--db PATH]
    --label LABEL --address ADDR --platform PLATFORM --allocation PCT
    [--multiplier MULT] [--enabled/--disabled]
    [--sizing-mode conviction|proportional]
    [--trade-size-pct PCT] [--aggregation-seconds N]
    [--history-window N] [--min-history N] [--cold-start-pct PCT]
```
Add a new target. Validates that the total allocation sum does not exceed 100%.

Conviction sizing options:
- `--sizing-mode`: `conviction` (default) or `proportional` (legacy ratio-based)
- `--trade-size-pct`: Base trade size as % of available budget (default 1.0)
- `--aggregation-seconds`: Seconds to batch signals before executing (default 7)
- `--history-window`: Number of recent trades for percentile calculation (default 50)
- `--min-history`: Minimum trades before conviction activates (default 10, hard minimum 10)
- `--cold-start-pct`: Budget % per trade during cold start, 0 = observe only (default 0)

```
python -m prediction_mirror targets enable LABEL [--db PATH]
python -m prediction_mirror targets disable LABEL [--db PATH]
```
Enable or disable a target. Disabled targets are not polled.

```
python -m prediction_mirror targets remove LABEL [--db PATH]
```
Remove a target.

```
python -m prediction_mirror targets set-allocation LABEL PCT [--db PATH]
```
Change a target's allocation percentage. Validates that the total does not exceed 100%.
