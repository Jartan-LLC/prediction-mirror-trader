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
@click.option("--no-dashboard", is_flag=True, help="Disable live dashboard, use log output")
@click.pass_context
def run(ctx, no_dashboard):
    """Start the mirror trading bot."""
    load_dotenv()
    db_path = ctx.obj["db_path"]
    conn = init_db(db_path)
    store = Store(conn)

    settings = store.get_settings()

    # Dashboard mode: TTY + not disabled
    use_dashboard = sys.stdout.isatty() and not no_dashboard

    # In dashboard mode, only log to file (dashboard owns the terminal)
    configure_logging(settings.log_level, console=not use_dashboard)

    from prediction_mirror.dashboard.listener import DashboardListener
    from prediction_mirror.engine.core import Engine
    from prediction_mirror.platforms import get_adapter_class
    from rich.live import Live

    # Build adapters for enabled targets
    adapters = {}
    targets = store.get_enabled_targets()
    for target in targets:
        if target.platform not in adapters:
            try:
                __import__(f"prediction_mirror.platforms.{target.platform}")
            except ImportError:
                console.print(f"[red]Unknown platform: {target.platform}[/red]")
                sys.exit(1)
            try:
                cls = get_adapter_class(target.platform)
                adapters[target.platform] = cls.from_env()
            except Exception as e:
                console.print(
                    f"[red]Failed to create adapter for {target.platform}: {e}[/red]"
                )
                sys.exit(1)

    async def _run():
        for adapter in adapters.values():
            await adapter.initialize()

        engine = Engine(store, adapters)

        if use_dashboard:
            live = Live(console=console, refresh_per_second=1, screen=False)
            live.start()
        else:
            live = None

        dashboard = DashboardListener(store, live=live)
        engine.add_listener(dashboard)

        loop = asyncio.get_event_loop()
        loop.add_signal_handler(
            signal_mod.SIGINT, lambda: asyncio.create_task(engine.shutdown())
        )
        loop.add_signal_handler(
            signal_mod.SIGTERM, lambda: asyncio.create_task(engine.shutdown())
        )

        try:
            await engine.run()
        finally:
            if live:
                live.stop()

    if not use_dashboard:
        console.print("[bold]Starting Prediction Mirror Trader[/bold]")
        console.print(f"  DB: {db_path}")
        mode = "[yellow]DRY RUN[/yellow]" if settings.dry_run else "[red]LIVE[/red]"
        console.print(f"  Mode: {mode}")
        console.print(f"  Targets: {len(targets)} enabled")

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    finally:
        from prediction_mirror.store.database import close
        close()
        if not use_dashboard:
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
    table.add_column("Mult", justify="right")
    table.add_column("Sizing")
    table.add_column("History", justify="right")
    table.add_column("Floor/Ceil", justify="right")
    table.add_column("Enabled", justify="center")

    from prediction_mirror.utils.formatting import fmt_address

    for t in all_targets:
        if t.sizing_mode == "conviction":
            sizing = f"conviction (cold {t.cold_start_pct:.0f}%)"
            history = f"{t.min_history}/{t.history_window}"
            floor_ceil = f"{t.conviction_floor_pct:.0f}-{t.conviction_ceiling_pct:.0f}%"
        else:
            sizing = "proportional"
            history = "-"
            floor_ceil = "-"
        table.add_row(
            t.label,
            t.platform,
            fmt_address(t.address),
            f"{t.allocation_pct:.1f}",
            f"{t.multiplier:.1f}",
            sizing,
            history,
            floor_ceil,
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
@click.option(
    "--sizing-mode", default="conviction", type=click.Choice(["conviction", "proportional"]),
    help="Sizing strategy (default: conviction)",
)
@click.option("--history-window", default=50, type=int, help="Trades in conviction history window")
@click.option("--min-history", default=10, type=int, help="Min trades before conviction activates")
@click.option("--cold-start-pct", default=50.0, type=float, help="Budget % during cold start")
@click.option("--conviction-floor", default=10.0, type=float, help="Min budget % per trade")
@click.option("--conviction-ceiling", default=90.0, type=float, help="Max budget % per trade")
@click.pass_context
def targets_add(
    ctx, label, address, platform, allocation, multiplier, enabled,
    sizing_mode, history_window, min_history, cold_start_pct,
    conviction_floor, conviction_ceiling,
):
    """Add a new target."""
    from prediction_mirror.models.target import TargetConfig

    conn = init_db(_resolve_db_path(ctx.obj.get("db_path")))
    store = Store(conn)
    try:
        target = TargetConfig(
            label=label, platform=platform, address=address,
            allocation_pct=allocation, multiplier=multiplier, enabled=enabled,
            sizing_mode=sizing_mode, history_window=history_window,
            min_history=min_history, cold_start_pct=cold_start_pct,
            conviction_floor_pct=conviction_floor,
            conviction_ceiling_pct=conviction_ceiling,
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
