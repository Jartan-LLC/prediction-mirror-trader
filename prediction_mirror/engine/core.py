from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from prediction_mirror.engine import executor, monitor, redeemer
from prediction_mirror.engine.listener import EngineListener
from prediction_mirror.models.signal import Signal, SignalType
from prediction_mirror.platforms.base import PlatformAdapter
from prediction_mirror.platforms.errors import TransientError

logger = logging.getLogger(__name__)


class Engine:
    """Core runtime: orchestrates monitor and redeemer loops."""

    def __init__(self, store, adapters: dict[str, PlatformAdapter]):
        self._store = store
        self._adapters = adapters
        self._listeners: list[EngineListener] = []
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._history_seeded: set[str] = set()

    def add_listener(self, listener: EngineListener) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener: EngineListener) -> None:
        self._listeners.remove(listener)

    def _dispatch(self, event_name: str, *args) -> None:
        for listener in self._listeners:
            try:
                method = getattr(listener, event_name, None)
                if method:
                    method(*args)
            except Exception:
                logger.exception(f"Listener error on {event_name}")

    async def run(self) -> None:
        """Start all loops, block until shutdown."""
        self._running = True
        self._dispatch("on_status_change", "running", "Engine started")

        self._tasks = [
            asyncio.create_task(self._monitor_loop()),
            asyncio.create_task(self._reconciliation_loop()),
            asyncio.create_task(self._redeemer_loop()),
            asyncio.create_task(self._dashboard_loop()),
        ]

        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            pass

    async def shutdown(self) -> None:
        """Graceful shutdown: cancel tasks, close adapters."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        for adapter in self._adapters.values():
            await adapter.shutdown()
        self._dispatch("on_status_change", "stopped", "Shutdown complete")

    async def _seed_trade_history(self, target, adapter) -> None:
        """Fetch historical trades from the platform and seed trade history."""
        try:
            trade_values = await adapter.fetch_trade_history(
                target.address, target.history_window
            )
            if trade_values:
                now = datetime.now(timezone.utc)
                for usd in trade_values:
                    self._store.record_observed_trade(target.label, usd, now)
                logger.info(
                    f"Seeded {len(trade_values)} historical trades "
                    f"for {target.label}"
                )
            else:
                logger.info(f"No historical trades found for {target.label}")
        except Exception as e:
            logger.warning(
                f"Failed to seed trade history for {target.label}: {e}"
            )

    async def _monitor_loop(self) -> None:
        while self._running:
            settings = self._store.get_settings()
            targets = self._store.get_enabled_targets()

            for target in targets:
                adapter = self._adapters.get(target.platform)
                if adapter is None:
                    continue

                # Seed trade history on first encounter
                if target.label not in self._history_seeded:
                    self._history_seeded.add(target.label)
                    await self._seed_trade_history(target, adapter)

                try:
                    signals = await monitor.poll_activity(
                        target, adapter, self._store
                    )
                    if signals:
                        await executor.handle_signals(
                            signals, adapter, self._store, settings,
                            dispatch=self._dispatch,
                        )
                except TransientError as e:
                    self._dispatch(
                        "on_error", str(e),
                        {"target": target.label, "transient": True},
                    )
                except Exception as e:
                    self._dispatch(
                        "on_error", str(e),
                        {"target": target.label, "transient": False},
                    )
                    logger.exception(f"Error polling target {target.label}")

            await asyncio.sleep(settings.poll_interval_seconds)

    async def _reconciliation_loop(self) -> None:
        """Retry pending goals when market conditions improve."""
        while self._running:
            settings = self._store.get_settings()
            pending = self._store.get_pending_goals()

            if pending:
                targets = {
                    t.label: t for t in self._store.get_enabled_targets()
                }
                for goal in pending:
                    target = targets.get(goal["target_label"])
                    if not target:
                        continue
                    adapter = self._adapters.get(goal["platform"])
                    if not adapter:
                        continue

                    net = goal["net_delta"]

                    # Only sell goals should exist, but guard against stale buys
                    if net > 0:
                        self._store.delete_goal(
                            goal["target_label"], goal["market_id"],
                            goal["asset_id"],
                        )
                        continue

                    # Check if we still hold this position
                    our_pos = self._store.get_position(
                        goal["market_id"], goal["asset_id"],
                        goal["target_label"],
                    )
                    if our_pos is None or our_pos.size <= 0:
                        # Nothing to sell — delete the goal
                        self._store.delete_goal(
                            goal["target_label"], goal["market_id"],
                            goal["asset_id"],
                        )
                        continue

                    synthetic = Signal(
                        signal_type=SignalType.SELL,
                        target=target,
                        platform=goal["platform"],
                        market_id=goal["market_id"],
                        asset_id=goal["asset_id"],
                        outcome=goal["outcome"],
                        target_delta=abs(net),
                        target_prev_size=0.0,
                        target_price=goal["vwap"],
                        detected_at=datetime.now(timezone.utc),
                    )

                    try:
                        results = await executor.handle_signals(
                            [synthetic], adapter, self._store, settings,
                            dispatch=self._dispatch,
                            track_goals=False,
                        )
                    except Exception as e:
                        logger.warning(
                            f"Reconciliation error for "
                            f"{goal['target_label']} "
                            f"{goal['asset_id'][:12]}: {e}"
                        )

            await asyncio.sleep(settings.poll_interval_seconds)

    async def _redeemer_loop(self) -> None:
        while self._running:
            settings = self._store.get_settings()
            try:
                await redeemer.run_redeemer_pass(
                    self._adapters, self._store, dispatch=self._dispatch,
                )
            except Exception as e:
                self._dispatch(
                    "on_error", str(e),
                    {"component": "redeemer", "transient": False},
                )
                logger.exception("Error in redeemer pass")

            await asyncio.sleep(settings.redeemer_interval_seconds)

    async def _dashboard_loop(self) -> None:
        while self._running:
            settings = self._store.get_settings()
            for listener in self._listeners:
                render = getattr(listener, "render", None)
                if render:
                    try:
                        render()
                    except Exception:
                        logger.exception("Dashboard render error")
            await asyncio.sleep(settings.dashboard_refresh_seconds)
