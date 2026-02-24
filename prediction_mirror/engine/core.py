from __future__ import annotations

import asyncio
import logging

from prediction_mirror.engine import executor, monitor, redeemer
from prediction_mirror.engine.listener import EngineListener
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

                try:
                    signals = await monitor.poll_target(target, adapter, self._store)
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

    async def _redeemer_loop(self) -> None:
        while self._running:
            settings = self._store.get_settings()
            try:
                await redeemer.run_redeemer_pass(
                    self._adapters, self._store, dispatch=self._dispatch,
                )
            except Exception as e:
                self._dispatch(
                    "on_error", str(e), {"component": "redeemer", "transient": False},
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
