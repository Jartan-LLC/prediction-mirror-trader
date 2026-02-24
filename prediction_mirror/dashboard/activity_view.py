from __future__ import annotations

import sqlite3

from rich.table import Table


def render_recent_signals(signals: list[sqlite3.Row], n: int = 10) -> Table:
    """Render recent signals table."""
    table = Table(title="RECENT SIGNALS", expand=True)
    table.add_column("Time", style="dim", width=19)
    table.add_column("Type")
    table.add_column("Target")
    table.add_column("Outcome")
    table.add_column("Delta", justify="right")

    for row in signals[:n]:
        sig_type = row["signal_type"]
        style = "green" if sig_type == "BUY" else "red"
        detected = row["detected_at"][:19] if row["detected_at"] else ""
        table.add_row(
            detected,
            f"[{style}]{sig_type}[/{style}]",
            row["target_label"],
            row["outcome"],
            f"{row['target_delta']:.1f}",
        )
    return table


def render_recent_trades(trades: list[sqlite3.Row], n: int = 10) -> Table:
    """Render recent trades table."""
    table = Table(title="RECENT TRADES", expand=True)
    table.add_column("Time", style="dim", width=19)
    table.add_column("Side")
    table.add_column("Target")
    table.add_column("Size", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Status")
    table.add_column("Dry", justify="center")

    for row in trades[:n]:
        side = row["side"]
        style = "green" if side == "BUY" else "red"
        executed = row["executed_at"][:19] if row["executed_at"] else ""
        status = "[green]OK[/green]" if row["success"] else f"[red]{row['error'] or 'FAIL'}[/red]"
        fill = f"{row['fill_size']:.1f}" if row["fill_size"] else "-"
        price = f"${row['fill_price']:.2f}" if row["fill_price"] else "-"
        table.add_row(
            executed,
            f"[{style}]{side}[/{style}]",
            row["target_label"],
            fill,
            price,
            status,
            "Y" if row["dry_run"] else "",
        )
    return table


def render_errors(errors: list[tuple[str, dict]], n: int = 5) -> Table:
    """Render recent errors."""
    table = Table(title=f"ERRORS ({len(errors)})", expand=True)
    table.add_column("Error", style="red")
    table.add_column("Context", style="dim")

    for msg, ctx in errors[-n:]:
        ctx_str = ", ".join(f"{k}={v}" for k, v in ctx.items())
        table.add_row(msg[:80], ctx_str[:40])
    return table
