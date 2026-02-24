from __future__ import annotations

import logging
import time
from collections import deque
from datetime import timedelta

from prediction_mirror.models.order import OrderResult
from prediction_mirror.models.position import OurPosition
from prediction_mirror.models.signal import Signal

logger = logging.getLogger(__name__)


class DashboardListener:
    """Implements EngineListener protocol. Collects events for dashboard rendering."""

    def __init__(self, store, max_errors: int = 50):
        self._store = store
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

    def on_signal(self, signal: Signal) -> None:
        logger.info(
            f"Signal {signal.signal_type.value} {signal.target.label} "
            f"{signal.outcome}@{signal.market_id[:12]}.. "
            f"delta={signal.target_delta:.2f} @ ${signal.target_price:.3f}"
        )

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

    def on_position_update(self, position: OurPosition) -> None:
        logger.info(
            f"Position {position.source_target} "
            f"{position.outcome}@{position.market_id[:12]}.. "
            f"size={position.size:.2f} avg=${position.avg_entry_price:.3f}"
        )

    def on_redeemed(self, position: OurPosition, pnl: float) -> None:
        logger.info(
            f"Redeemed {position.source_target} "
            f"{position.outcome}@{position.market_id[:12]}.. "
            f"P&L=${pnl:+.2f}"
        )

    def on_error(self, error: str, context: dict) -> None:
        self._errors.append((error, context))
        ctx_str = ", ".join(f"{k}={v}" for k, v in context.items())
        logger.warning(f"Error: {error} ({ctx_str})")

    def on_status_change(self, status: str, detail: str) -> None:
        self._status = status
        logger.info(f"Status: {status} — {detail}")
