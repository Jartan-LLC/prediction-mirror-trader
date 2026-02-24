"""CLI entry point for prediction_mirror."""
from __future__ import annotations

import asyncio
import os
import signal as signal_mod
import sys

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from prediction_mirror.store import Store, init_db
from prediction_mirror.utils.log import configure_logging

console = Console()

DEFAULT_DB_PATH = "prediction_mirror.db"


def _resolve_db_path(db: str | None) -> str:
    if db:
        return db
    return os.environ.get("PMT_DB_PATH", DEFAULT_DB_PATH)


@click.group()
@click.option("--db", default=None, help="Database path (default: PMT_DB_PATH env or ./prediction_mirror.db)")
@click.pass_context
def cli(ctx, db):
    """Prediction Mirror Trader — mirror prediction market positions."""
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = _resolve_db_path(db)


@cli.command()
@click.pass_context
def run(ctx):
    """Start the mirror trading bot."""
    load_dotenv()
    db_path = ctx.obj["db_path"]
    conn = init_db(db_path)
    store = Store(conn)

    settings = store.get_settings()
    configure_logging(settings.log_level)

    from prediction_mirror.dashboard.listener import DashboardListener
    from prediction_mirror.engine.core import Engine
    from prediction_mirror.platforms import get_adapter_class

    # Build adapters for enabled targets
    adapters = {}
    targets = store.get_enabled_targets()
    for target in targets:
        if target.platform not in adapters:
            # Import platform module to trigger registration
            try:
                __import__(f"prediction_mirror.platforms.{target.platform}")
            except ImportError:
                console.print(f"[red]Unknown platform: {target.platform}[/red]")
                sys.exit(1)
            try:
                cls = get_adapter_class(target.platform)
                adapters[target.platform] = cls.from_env()
            except Exception as e:
                console.print(f"[red]Failed to create adapter for {target.platform}: {e}[/red]")
                sys.exit(1)

    engine = Engine(store, adapters)
    dashboard = DashboardListener(store)
    engine.add_listener(dashboard)

    console.print(f"[bold]Starting Prediction Mirror Trader[/bold]")
    console.print(f"  DB: {db_path}")
    console.print(f"  Mode: {'[yellow]DRY RUN[/yellow]' if settings.dry_run else '[red]LIVE[/red]'}")
    console.print(f"  Targets: {len(targets)} enabled")

    async def _run():
        for adapter in adapters.values():
            await adapter.initialize()

        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal_mod.SIGINT, lambda: asyncio.create_task(engine.shutdown()))
        loop.add_signal_handler(signal_mod.SIGTERM, lambda: asyncio.create_task(engine.shutdown()))

        await engine.run()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    finally:
        from prediction_mirror.store.database import close
        close()
        console.print("[dim]Shutdown complete.[/dim]")


# ── Settings commands ──


@cli.group()
def settings():
    """Manage bot settings."""


@settings.command("list")
@click.pass_context
def settings_list(ctx):
    """Show all settings."""
    conn = init_db(_resolve_db_path(ctx.obj.get("db_path")))
    store = Store(conn)
    all_settings = store.get_all_settings()

    table = Table(title="Settings")
    table.add_column("Key", style="cyan")
    table.add_column("Value")

    for key, value in all_settings:
        table.add_row(key, value)

    console.print(table)
    conn.close()


@settings.command("set")
@click.argument("key")
@click.argument("value")
@click.pass_context
def settings_set(ctx, key, value):
    """Update a setting."""
    conn = init_db(_resolve_db_path(ctx.obj.get("db_path")))
    store = Store(conn)
    try:
        store.set_setting(key, value)
        console.print(f"[green]Set {key} = {value}[/green]")
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    except ValueError as e:
        console.print(f"[red]Invalid value: {e}[/red]")
        sys.exit(1)
    finally:
        conn.close()


# ── Targets commands ──


@cli.group()
def targets():
    """Manage mirror targets."""


@targets.command("list")
@click.pass_context
def targets_list(ctx):
    """Show all targets."""
    conn = init_db(_resolve_db_path(ctx.obj.get("db_path")))
    store = Store(conn)
    all_targets = store.get_all_targets()

    table = Table(title="Targets")
    table.add_column("Label", style="cyan")
    table.add_column("Platform")
    table.add_column("Address", max_width=20)
    table.add_column("Alloc %", justify="right")
    table.add_column("Multiplier", justify="right")
    table.add_column("Enabled", justify="center")

    from prediction_mirror.utils.formatting import fmt_address

    for t in all_targets:
        table.add_row(
            t.label,
            t.platform,
            fmt_address(t.address),
            f"{t.allocation_pct:.1f}",
            f"{t.multiplier:.1f}",
            "[green]Yes[/green]" if t.enabled else "[red]No[/red]",
        )

    console.print(table)
    conn.close()


@targets.command("add")
@click.option("--label", required=True, help="Human-readable name")
@click.option("--address", required=True, help="Wallet address")
@click.option("--platform", required=True, help="Platform name (e.g. polymarket)")
@click.option("--allocation", required=True, type=float, help="Budget allocation %")
@click.option("--multiplier", default=1.0, type=float, help="Sizing multiplier")
@click.option("--enabled/--disabled", default=True)
@click.pass_context
def targets_add(ctx, label, address, platform, allocation, multiplier, enabled):
    """Add a new target."""
    from prediction_mirror.models.target import TargetConfig

    conn = init_db(_resolve_db_path(ctx.obj.get("db_path")))
    store = Store(conn)
    try:
        target = TargetConfig(
            label=label, platform=platform, address=address,
            allocation_pct=allocation, multiplier=multiplier, enabled=enabled,
        )
        store.add_target(target)
        console.print(f"[green]Added target: {label}[/green]")
    except (ValueError, Exception) as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    finally:
        conn.close()


@targets.command("enable")
@click.argument("label")
@click.pass_context
def targets_enable(ctx, label):
    """Enable a target."""
    conn = init_db(_resolve_db_path(ctx.obj.get("db_path")))
    store = Store(conn)
    try:
        store.enable_target(label)
        console.print(f"[green]Enabled: {label}[/green]")
    except (KeyError, ValueError) as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    finally:
        conn.close()


@targets.command("disable")
@click.argument("label")
@click.pass_context
def targets_disable(ctx, label):
    """Disable a target."""
    conn = init_db(_resolve_db_path(ctx.obj.get("db_path")))
    store = Store(conn)
    try:
        store.disable_target(label)
        console.print(f"[yellow]Disabled: {label}[/yellow]")
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    finally:
        conn.close()


@targets.command("remove")
@click.argument("label")
@click.pass_context
def targets_remove(ctx, label):
    """Remove a target."""
    conn = init_db(_resolve_db_path(ctx.obj.get("db_path")))
    store = Store(conn)
    try:
        store.remove_target(label)
        console.print(f"[yellow]Removed: {label}[/yellow]")
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    finally:
        conn.close()


@targets.command("set-allocation")
@click.argument("label")
@click.argument("pct", type=float)
@click.pass_context
def targets_set_allocation(ctx, label, pct):
    """Change a target's allocation percentage."""
    conn = init_db(_resolve_db_path(ctx.obj.get("db_path")))
    store = Store(conn)
    try:
        store.set_allocation(label, pct)
        console.print(f"[green]Set {label} allocation to {pct:.1f}%[/green]")
    except (KeyError, ValueError) as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    finally:
        conn.close()


def main():
    cli()


if __name__ == "__main__":
    main()
