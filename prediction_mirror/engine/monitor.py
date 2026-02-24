from __future__ import annotations

from datetime import datetime, timezone

from prediction_mirror.models.position import TargetPosition
from prediction_mirror.models.signal import Signal, SignalType
from prediction_mirror.models.target import TargetConfig
import logging

logger = logging.getLogger(__name__)

# Targets that have been baselined this run. Reset on every bot restart,
# so we always re-snapshot current state and only mirror changes from
# this point forward (no catch-up on trades missed while the bot was down).
_baselined: set[str] = set()


def diff_positions(
    old: list[TargetPosition],
    new: list[TargetPosition],
    target: TargetConfig,
    dust_threshold: float = 0.01,
) -> list[Signal]:
    """Pure function: diff old vs new positions, return signals.

    No I/O, no side effects. Keys positions by (market_id, asset_id).
    """
    old_map = {(p.market_id, p.asset_id): p for p in old}
    new_map = {(p.market_id, p.asset_id): p for p in new}

    signals: list[Signal] = []
    now = datetime.now(timezone.utc)

    # Check new or increased positions
    for key, new_pos in new_map.items():
        old_pos = old_map.get(key)
        old_size = old_pos.size if old_pos else 0.0
        delta = new_pos.size - old_size

        if abs(delta) < dust_threshold:
            continue

        if delta > 0:
            signals.append(Signal(
                signal_type=SignalType.BUY,
                target=target,
                platform=new_pos.platform,
                market_id=new_pos.market_id,
                asset_id=new_pos.asset_id,
                outcome=new_pos.outcome,
                target_delta=delta,
                target_prev_size=old_size,
                target_price=new_pos.current_price,
                detected_at=now,
            ))
        elif delta < 0:
            signals.append(Signal(
                signal_type=SignalType.SELL,
                target=target,
                platform=new_pos.platform,
                market_id=new_pos.market_id,
                asset_id=new_pos.asset_id,
                outcome=new_pos.outcome,
                target_delta=abs(delta),
                target_prev_size=old_size,
                target_price=new_pos.current_price,
                detected_at=now,
            ))

    # Check positions that disappeared (full exit)
    for key, old_pos in old_map.items():
        if key not in new_map and old_pos.size >= dust_threshold:
            signals.append(Signal(
                signal_type=SignalType.SELL,
                target=target,
                platform=old_pos.platform,
                market_id=old_pos.market_id,
                asset_id=old_pos.asset_id,
                outcome=old_pos.outcome,
                target_delta=old_pos.size,
                target_prev_size=old_pos.size,
                target_price=old_pos.current_price,
                detected_at=now,
            ))

    return signals


async def poll_target(
    target: TargetConfig,
    adapter,
    store,
) -> list[Signal]:
    """Fetch current positions, diff against snapshot, return signals."""
    new_positions = await adapter.fetch_target_positions(target.address)

    # On the first poll this run, snapshot current state as baseline.
    # This ensures we never try to catch up on trades missed while
    # the bot was down — we only mirror changes from now on.
    target_key = f"{target.platform}:{target.address}"
    if target_key not in _baselined:
        _baselined.add(target_key)
        logger.info(
            f"Baseline for {target.label}: {len(new_positions)} positions "
            f"(no signals generated)"
        )
        for pos in new_positions:
            store.upsert_snapshot(pos)
        return []

    old_positions = store.get_all_snapshots(target.address)
    signals = diff_positions(old_positions, new_positions, target)

    # Update snapshots
    for pos in new_positions:
        store.upsert_snapshot(pos)

    return signals
