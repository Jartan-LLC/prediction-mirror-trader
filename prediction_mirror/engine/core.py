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


def merge_signals(signals: list[Signal]) -> list[Signal]:
    """Merge signals for the same market+asset+direction by summing deltas."""
    merged: dict[tuple, Signal] = {}
    for sig in signals:
        key = (sig.market_id, sig.asset_id, sig.signal_type)
        if key in merged:
            existing = merged[key]
            # Sum deltas, keep the latest price and timestamp
            merged[key] = Signal(
                signal_type=sig.signal_type,
                target=sig.target,
                platform=sig.platform,
                market_id=sig.market_id,
                asset_id=sig.asset_id,
                outcome=sig.outcome,
                target_delta=existing.target_delta + sig.target_delta,
                target_prev_size=existing.target_prev_size,
                target_price=sig.target_price,
                detected_at=sig.detected_at,
            )
        else:
            merged[key] = sig
    return list(merged.values())


class Engine:
    """Core runtime: orchestrates monitor and redeemer loops."""

    def __init__(self, store, adapters: dict[str, PlatformAdapter]):
        self._store = store
        self._adapters = adapters
        self._listeners: list[EngineListener] = []
        self._running = False
        self._tasks: list[asyncio.Task] = []
        # Signal aggregation buffer: target_label → (signals, last_update_time)
        self._signal_buffer: dict[str, tuple[list[Signal], float]] = {}
        # Targets whose trade history has been seeded this run
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
            asyncio.create_task(self._aggregation_loop()),
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

    async def _monitor_loop(self) -> None:
        while self._running:
            settings = self._store.get_settings()
            targets = self._store.get_enabled_targets()

            for target in targets:
                adapter = self._adapters.get(target.platform)
                if adapter is None:
                    continue

                # Seed trade history from Data API on first poll
                if target.label not in self._history_seeded:
                    self._history_seeded.add(target.label)
                    await self._seed_trade_history(target, adapter)

                try:
                    signals = await monitor.poll_target(
                        target, adapter, self._store
                    )
                    if signals:
                        self._buffer_signals(target.label, signals)
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

    def _buffer_signals(self, target_label: str, signals: list[Signal]) -> None:
        """Add signals to the aggregation buffer for this target."""
        now = time.monotonic()
        if target_label in self._signal_buffer:
            existing, _ = self._signal_buffer[target_label]
            existing.extend(signals)
            self._signal_buffer[target_label] = (existing, now)
        else:
            self._signal_buffer[target_label] = (list(signals), now)

    async def _aggregation_loop(self) -> None:
        """Flush buffered signals once the aggregation window has elapsed."""
        while self._running:
            now = time.monotonic()
            settings = self._store.get_settings()
            targets = {t.label: t for t in self._store.get_enabled_targets()}

            labels_to_flush = []
            for label, (signals, last_update) in self._signal_buffer.items():
                target = targets.get(label)
                if target is None:
                    labels_to_flush.append(label)
                    continue
                window = target.aggregation_seconds
                if now - last_update >= window:
                    labels_to_flush.append(label)

            for label in labels_to_flush:
                signals, _ = self._signal_buffer.pop(label)
                target = targets.get(label)
                if not target or not signals:
                    continue

                merged = merge_signals(signals)
                adapter = self._adapters.get(target.platform)
                if adapter is None:
                    continue

                count = len(signals)
                if count != len(merged):
                    logger.info(
                        f"Aggregated {count} signals → {len(merged)} "
                        f"for {label}"
                    )

                try:
                    await executor.handle_signals(
                        merged, adapter, self._store, settings,
                        dispatch=self._dispatch,
                    )
                except Exception as e:
                    self._dispatch(
                        "on_error", str(e),
                        {"target": label, "transient": False},
                    )
                    logger.exception(f"Error executing signals for {label}")

            await asyncio.sleep(1)  # Check buffer every second

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
