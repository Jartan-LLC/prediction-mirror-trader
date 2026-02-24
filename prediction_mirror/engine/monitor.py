from __future__ import annotations

import logging
from datetime import datetime, timezone

from prediction_mirror.models.signal import Signal, SignalType
from prediction_mirror.models.target import TargetConfig

logger = logging.getLogger(__name__)


def _activity_to_signals(
    trades: list[dict], target: TargetConfig
) -> list[Signal]:
    """Convert raw activity trades to Signals, merging fragments.

    Trades for the same (market, asset, side) are merged: sizes summed,
    price is volume-weighted average.
    """
    # Group by (conditionId, asset, side)
    groups: dict[tuple, list[dict]] = {}
    for trade in trades:
        key = (
            trade.get("conditionId", ""),
            trade.get("asset", ""),
            trade.get("side", ""),
        )
        groups.setdefault(key, []).append(trade)

    signals: list[Signal] = []
    for (condition_id, asset_id, side), group in groups.items():
        total_size = sum(float(t.get("size", 0)) for t in group)
        total_usd = sum(float(t.get("usdcSize", 0)) for t in group)
        # Volume-weighted average price
        vwap = total_usd / total_size if total_size > 0 else 0.0
        latest_ts = max(int(t.get("timestamp", 0)) for t in group)
        outcome = group[0].get("outcome", "")

        if total_size <= 0:
            continue

        signal_type = SignalType.BUY if side == "BUY" else SignalType.SELL

        signals.append(Signal(
            signal_type=signal_type,
            target=target,
            platform=target.platform,
            market_id=condition_id,
            asset_id=asset_id,
            outcome=outcome,
            target_delta=total_size,
            target_prev_size=0.0,
            target_price=vwap,
            detected_at=datetime.fromtimestamp(latest_ts, tz=timezone.utc),
        ))

    return signals


async def poll_activity(
    target: TargetConfig,
    adapter,
    store,
) -> list[Signal]:
    """Fetch new trades from /activity since last check, return merged signals."""
    from prediction_mirror.store.targets import (
        get_last_activity_ts,
        update_activity_ts,
    )

    last_ts = get_last_activity_ts(store.conn, target.label)

    if last_ts == 0:
        # First poll — set to now, don't replay old trades
        import time
        now_ts = int(time.time())
        update_activity_ts(store.conn, target.label, now_ts)
        logger.info(
            f"Initialized activity tracking for {target.label} "
            f"(starting from now)"
        )
        return []

    trades = await adapter.fetch_activity_since(target.address, last_ts)

    if not trades:
        return []

    # Update last_activity_ts to the latest trade
    max_ts = max(int(t.get("timestamp", 0)) for t in trades)
    update_activity_ts(store.conn, target.label, max_ts)

    # Record trade USD values for conviction history
    for trade in trades:
        usd = float(trade.get("usdcSize", 0))
        if usd > 0:
            ts = datetime.fromtimestamp(
                int(trade.get("timestamp", 0)), tz=timezone.utc
            )
            store.record_observed_trade(target.label, usd, ts)

    signals = _activity_to_signals(trades, target)

    if signals:
        merged_note = ""
        if len(trades) != len(signals):
            merged_note = f" (merged from {len(trades)} trades)"
        logger.info(
            f"{target.label}: {len(signals)} signals{merged_note}"
        )

    return signals
