from __future__ import annotations

from rich.table import Table

from prediction_mirror.utils.formatting import fmt_pct, fmt_usd

MAX_POSITIONS_SHOWN = 6


def render_allocation_table(allocation_summary: dict[str, dict]) -> Table:
    """Render per-target allocation breakdown."""
    table = Table(title="ALLOCATION", expand=True)
    table.add_column("Target", style="cyan")
    table.add_column("Alloc", justify="right")
    table.add_column("Cash", justify="right")
    table.add_column("Deployed", justify="right")
    table.add_column("Total", justify="right", style="green")

    for label, info in allocation_summary.items():
        if label == "_reserve":
            table.add_row(
                "Reserve", "-",
                fmt_usd(info.get("available", 0)),
                "-", "-",
                style="dim",
            )
        else:
            table.add_row(
                label,
                fmt_pct(info.get("allocation_pct", 0)),
                fmt_usd(info.get("available", 0)),
                fmt_usd(info.get("deployed", 0)),
                fmt_usd(info.get("budget", 0)),
            )
    return table


def render_positions_table(
    positions: list, price_map: dict | None = None
) -> Table:
    """Render our current positions, sorted by value, capped."""
    price_map = price_map or {}

    sorted_pos = sorted(positions, key=lambda p: p.total_cost, reverse=True)
    shown = sorted_pos[:MAX_POSITIONS_SHOWN]
    hidden = len(sorted_pos) - len(shown)

    title = f"POSITIONS ({len(sorted_pos)})"

    table = Table(title=title, expand=True)
    table.add_column("Outcome", style="cyan")
    table.add_column("Size", justify="right")
    table.add_column("Entry", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("Value", justify="right")
    table.add_column("P&L", justify="right")
    table.add_column("Source", style="dim")

    for pos in shown:
        cur_price = price_map.get(pos.asset_id)
        if cur_price is not None and cur_price > 0:
            value = pos.size * cur_price
            pnl = value - pos.total_cost
            pnl_style = "green" if pnl >= 0 else "red"
            value_str = fmt_usd(value)
            pnl_str = f"[{pnl_style}]{fmt_usd(pnl)}[/{pnl_style}]"
        else:
            value_str = "-"
            pnl_str = "-"

        table.add_row(
            pos.outcome,
            f"{pos.size:.1f}",
            fmt_usd(pos.avg_entry_price),
            fmt_usd(pos.total_cost),
            value_str,
            pnl_str,
            pos.source_target,
        )

    if hidden > 0:
        table.add_row(
            f"... +{hidden} more", "", "", "", "", "", "",
            style="dim",
        )

    return table
