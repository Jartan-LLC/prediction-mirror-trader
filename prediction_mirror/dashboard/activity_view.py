from __future__ import annotations

import sqlite3

from rich.table import Table

from prediction_mirror.utils.formatting import fmt_usd


def render_recent_signals(signals: list[sqlite3.Row], n: int = 5) -> Table:
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


def render_recent_trades(trades: list[sqlite3.Row], n: int = 5) -> Table:
    """Render recent trades table."""
    table = Table(title="RECENT TRADES", expand=True)
    table.add_column("Time", style="dim", width=19)
    table.add_column("Side")
    table.add_column("Target")
    table.add_column("Size", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("USD", justify="right")

    for row in trades[:n]:
        side = row["side"]
        style = "green" if side == "BUY" else "red"
        executed = row["executed_at"][:19] if row["executed_at"] else ""
        fill = f"{row['fill_size']:.1f}" if row["fill_size"] else "-"
        price = f"${row['fill_price']:.2f}" if row["fill_price"] else "-"
        usd = fmt_usd(row["usd_amount"]) if row["usd_amount"] else "-"
        table.add_row(
            executed,
            f"[{style}]{side}[/{style}]",
            row["target_label"],
            fill,
            price,
            usd,
        )
    return table


def render_pending_goals(goals: list[sqlite3.Row], n: int = 5) -> Table:
    """Render pending reconciliation goals."""
    table = Table(title=f"PENDING GOALS ({len(goals)})", expand=True)
    table.add_column("Target")
    table.add_column("Outcome")
    table.add_column("Side")
    table.add_column("Delta", justify="right")
    table.add_column("VWAP", justify="right")
    table.add_column("USD", justify="right")

    for goal in goals[:n]:
        net = goal["net_delta"]
        side = "BUY" if net > 0 else "SELL"
        style = "green" if side == "BUY" else "red"
        table.add_row(
            goal["target_label"],
            goal["outcome"],
            f"[{style}]{side}[/{style}]",
            f"{abs(net):.1f}",
            f"${goal['vwap']:.3f}",
            fmt_usd(goal["total_usd"]),
        )
    return table


def render_errors(errors: list[tuple[str, dict]], n: int = 3) -> Table:
    """Render recent errors."""
    table = Table(title=f"ERRORS ({len(errors)})", expand=True)
    table.add_column("Error", style="red")
    table.add_column("Context", style="dim")

    for msg, ctx in errors[-n:]:
        ctx_str = ", ".join(f"{k}={v}" for k, v in ctx.items())
        table.add_row(msg[:80], ctx_str[:40])
    return table
