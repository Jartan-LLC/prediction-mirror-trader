from __future__ import annotations

import logging
import time
from collections import deque
from datetime import timedelta

from rich.live import Live

from prediction_mirror.dashboard.renderer import render_dashboard
from prediction_mirror.models.order import OrderResult
from prediction_mirror.models.position import OurPosition
from prediction_mirror.models.signal import Signal

logger = logging.getLogger(__name__)


class DashboardListener:
    """Implements EngineListener protocol. Drives rich.live.Live dashboard or logs."""

    def __init__(self, store, live: Live | None = None, max_errors: int = 50):
        self._store = store
        self._live = live
        self._start_time = time.monotonic()
        self._errors: deque[tuple[str, dict]] = deque(maxlen=max_errors)
        self._status = "starting"

    @property
    def uptime(self) -> str:
        elapsed = time.monotonic() - self._start_time
        td = timedelta(seconds=int(elapsed))
        hours, remainder = divmod(td.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        if td.days:
            return f"{td.days}d {hours}h {minutes}m"
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    @property
    def status(self) -> str:
        return self._status

    @property
    def errors(self) -> list[tuple[str, dict]]:
        return list(self._errors)

    def render(self) -> None:
        """Re-render the dashboard. Called periodically and on events."""
        if not self._live:
            return

        settings = self._store.get_settings()
        targets = self._store.get_all_targets()
        positions = [p for p in self._store.get_all_positions() if p.size > 0]
        recent_signals = self._store.get_signal_history(limit=10)
        recent_trades = self._store.get_recent_trades(limit=10)

        if settings.dry_run:
            portfolio_value = settings.dry_run_balance_usd
        else:
            # Real mode: liquid balance would come from wallet state,
            # but for dashboard we approximate from deployed
            portfolio_value = self._store.get_total_deployed(dry_run=False)
        allocation = self._store.get_allocation_summary(
            targets, portfolio_value, dry_run=settings.dry_run,
        )

        panel = render_dashboard(
            uptime=self.uptime,
            dry_run=settings.dry_run,
            target_count=len([t for t in targets if t.enabled]),
            allocation_summary=allocation,
            positions=positions,
            signals=recent_signals,
            trades=recent_trades,
            errors=self.errors,
        )
        self._live.update(panel)

    def on_signal(self, signal: Signal) -> None:
        logger.info(
            f"Signal {signal.signal_type.value} {signal.target.label} "
            f"{signal.outcome}@{signal.market_id[:12]}.. "
            f"delta={signal.target_delta:.2f} @ ${signal.target_price:.3f}"
        )
        self.render()

    def on_trade(self, result: OrderResult) -> None:
        order = result.order
        mode = "PAPER" if order.dry_run else "LIVE"
        if result.success:
            logger.info(
                f"{mode} {order.side.value} {order.signal.target.label} "
                f"{order.signal.outcome}@{order.signal.market_id[:12]}.. "
                f"{result.fill_size:.2f} shares @ ${result.fill_price:.3f} "
                f"(${order.usd_amount:.2f})"
            )
        else:
            logger.warning(
                f"{mode} FAILED {order.side.value} {order.signal.target.label} "
                f"{order.signal.outcome}@{order.signal.market_id[:12]}.. "
                f"— {result.error}"
            )
        self.render()

    def on_position_update(self, position: OurPosition) -> None:
        logger.info(
            f"Position {position.source_target} "
            f"{position.outcome}@{position.market_id[:12]}.. "
            f"size={position.size:.2f} avg=${position.avg_entry_price:.3f}"
        )
        self.render()

    def on_redeemed(self, position: OurPosition, pnl: float) -> None:
        logger.info(
            f"Redeemed {position.source_target} "
            f"{position.outcome}@{position.market_id[:12]}.. "
            f"P&L=${pnl:+.2f}"
        )
        self.render()

    def on_error(self, error: str, context: dict) -> None:
        self._errors.append((error, context))
        ctx_str = ", ".join(f"{k}={v}" for k, v in context.items())
        logger.warning(f"Error: {error} ({ctx_str})")
        self.render()

    def on_status_change(self, status: str, detail: str) -> None:
        self._status = status
        logger.info(f"Status: {status} — {detail}")
        self.render()
