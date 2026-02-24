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
        pass  # Signals retrieved from store for rendering

    def on_trade(self, result: OrderResult) -> None:
        pass  # Trades retrieved from store for rendering

    def on_position_update(self, position: OurPosition) -> None:
        pass  # Positions retrieved from store for rendering

    def on_redeemed(self, position: OurPosition, pnl: float) -> None:
        pass

    def on_error(self, error: str, context: dict) -> None:
        self._errors.append((error, context))

    def on_status_change(self, status: str, detail: str) -> None:
        self._status = status
