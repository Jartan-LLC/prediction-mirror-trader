from __future__ import annotations

from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from prediction_mirror.dashboard.activity_view import (
    render_errors,
    render_recent_signals,
    render_recent_trades,
)
from prediction_mirror.dashboard.portfolio_view import (
    render_allocation_table,
    render_positions_table,
)


def render_header(uptime: str, dry_run: bool, target_count: int) -> Text:
    mode = "[DRY RUN]" if dry_run else "[LIVE]"
    header = Text()
    header.append("PREDICTION MIRROR TRADER  ", style="bold white")
    header.append(mode, style="bold yellow" if dry_run else "bold red")
    header.append(f"  {target_count} targets", style="dim")
    header.append(f"  |  Uptime: {uptime}", style="dim")
    return header


def render_dashboard(
    uptime: str,
    dry_run: bool,
    target_count: int,
    allocation_summary: dict,
    positions: list,
    signals: list,
    trades: list,
    errors: list,
) -> Panel:
    """Compose the full dashboard as a rich Panel."""
    header = render_header(uptime, dry_run, target_count)
    alloc_table = render_allocation_table(allocation_summary)
    pos_table = render_positions_table(positions)
    sig_table = render_recent_signals(signals)
    trade_table = render_recent_trades(trades)
    err_table = render_errors(errors)

    return Panel(
        Group(header, "", alloc_table, "", pos_table, "", sig_table, "", trade_table, "", err_table),
        expand=True,
    )
