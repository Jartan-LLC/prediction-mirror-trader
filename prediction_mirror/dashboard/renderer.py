from __future__ import annotations

from rich.columns import Columns
from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from prediction_mirror.dashboard.activity_view import (
    render_errors,
    render_pending_goals,
    render_recent_signals,
    render_recent_trades,
)
from prediction_mirror.dashboard.portfolio_view import (
    render_allocation_table,
    render_positions_table,
)


def render_header(
    uptime: str, dry_run: bool, target_count: int, total_pnl: float | None = None,
) -> Text:
    mode = "[DRY RUN]" if dry_run else "[LIVE]"
    header = Text()
    header.append("PREDICTION MIRROR TRADER  ", style="bold white")
    header.append(mode, style="bold yellow" if dry_run else "bold red")
    header.append(f"  {target_count} targets", style="dim")
    header.append(f"  |  Uptime: {uptime}", style="dim")
    if total_pnl is not None:
        pnl_style = "bold green" if total_pnl >= 0 else "bold red"
        sign = "+" if total_pnl >= 0 else ""
        header.append(f"  |  P&L: {sign}${total_pnl:.2f}", style=pnl_style)
    return header


def render_dashboard(
    uptime: str,
    dry_run: bool,
    target_count: int,
    allocation_summary: dict,
    positions: list,
    price_map: dict | None = None,
    signals: list = None,
    trades: list = None,
    goals: list = None,
    errors: list = None,
) -> Panel:
    """Compose the full dashboard as a rich Panel."""
    signals = signals or []
    trades = trades or []
    goals = goals or []
    errors = errors or []
    # Calculate total P&L from positions with known prices
    total_pnl = None
    if price_map and positions:
        pnl_sum = 0.0
        has_prices = False
        for pos in positions:
            cur = price_map.get(pos.asset_id)
            if cur is not None and cur > 0:
                pnl_sum += (pos.size * cur) - pos.total_cost
                has_prices = True
        if has_prices:
            total_pnl = pnl_sum

    header = render_header(uptime, dry_run, target_count, total_pnl)
    alloc_table = render_allocation_table(allocation_summary)
    pos_table = render_positions_table(positions, price_map=price_map)
    trade_table = render_recent_trades(trades)
    sig_table = render_recent_signals(signals)

    sections = [header, "", alloc_table, "", pos_table, "", trade_table]

    # Signals and goals side by side
    side_by_side = [sig_table]
    if goals:
        side_by_side.append(render_pending_goals(goals))
    sections.extend(["", Columns(side_by_side, equal=True, expand=True)])

    if errors:
        sections.extend(["", render_errors(errors)])

    return Panel(Group(*sections), expand=True)
