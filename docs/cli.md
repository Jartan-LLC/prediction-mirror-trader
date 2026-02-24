# CLI Reference

All subcommands accept `--db PATH` (default: `PMT_DB_PATH` env var, or `./prediction_mirror.db`).

## Bot Control

```
python -m prediction_mirror run [--db PATH]
```

Start the bot. Creates the database and seeds default settings on first run.

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
Display all targets with allocation info, enabled status, and deployed capital.

```
python -m prediction_mirror targets add [--db PATH]
    --label LABEL --address ADDR --platform PLATFORM --allocation PCT
    [--multiplier MULT] [--enabled]
```
Add a new target. Validates that the total allocation sum does not exceed 100%.

```
python -m prediction_mirror targets enable LABEL [--db PATH]
python -m prediction_mirror targets disable LABEL [--db PATH]
```
Enable or disable a target. Disabled targets are not polled. Existing positions become unmirrored.

```
python -m prediction_mirror targets remove LABEL [--db PATH]
```
Remove a target. Existing positions become orphaned (no automatic selling).

```
python -m prediction_mirror targets set-allocation LABEL PCT [--db PATH]
```
Change a target's allocation percentage. Validates that the total does not exceed 100%.
