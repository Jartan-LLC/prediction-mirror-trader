from __future__ import annotations

from rich.table import Table

from prediction_mirror.utils.formatting import fmt_pct, fmt_usd


def render_allocation_table(allocation_summary: dict[str, dict]) -> Table:
    """Render per-target allocation breakdown."""
    table = Table(title="ALLOCATION", expand=True)
    table.add_column("Target", style="cyan")
    table.add_column("Alloc", justify="right")
    table.add_column("Budget", justify="right")
    table.add_column("Deployed", justify="right")
    table.add_column("Available", justify="right", style="green")

    for label, info in allocation_summary.items():
        if label == "_reserve":
            table.add_row(
                "Reserve", "-", "-", "-",
                fmt_usd(info.get("available", 0)),
                style="dim",
            )
        else:
            table.add_row(
                label,
                fmt_pct(info.get("allocation_pct", 0)),
                fmt_usd(info.get("budget", 0)),
                fmt_usd(info.get("deployed", 0)),
                fmt_usd(info.get("available", 0)),
            )
    return table


def render_positions_table(positions: list) -> Table:
    """Render our current positions."""
    table = Table(title=f"POSITIONS ({len(positions)})", expand=True)
    table.add_column("Market", style="cyan", max_width=30)
    table.add_column("Outcome")
    table.add_column("Size", justify="right")
    table.add_column("Entry", justify="right")
    table.add_column("Source", style="dim")
    table.add_column("Dry", justify="center")

    for pos in positions:
        table.add_row(
            pos.market_id[:28] + ".." if len(pos.market_id) > 30 else pos.market_id,
            pos.outcome,
            f"{pos.size:.1f}",
            fmt_usd(pos.avg_entry_price),
            pos.source_target,
            "Y" if pos.dry_run else "",
        )
    return table
