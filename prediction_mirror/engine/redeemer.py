from __future__ import annotations

import logging
from datetime import datetime, timezone

from prediction_mirror.models.market import MarketStatus
from prediction_mirror.models.order import OrderResult, OrderSide, SizedOrder
from prediction_mirror.models.position import OurPosition
from prediction_mirror.models.signal import Signal, SignalType
from prediction_mirror.models.target import TargetConfig
from prediction_mirror.platforms.base import PlatformAdapter
from prediction_mirror.platforms.errors import PlatformError

logger = logging.getLogger(__name__)


async def run_redeemer_pass(
    adapters: dict[str, PlatformAdapter],
    store,
    dispatch=None,
) -> None:
    """Check all positions for resolved markets, redeem or calculate P&L."""
    positions = store.get_all_positions()
    for pos in positions:
        if pos.size <= 0:
            continue

        adapter = adapters.get(pos.platform)
        if adapter is None:
            continue

        try:
            market = await adapter.fetch_market(pos.market_id)
        except PlatformError as e:
            logger.warning(f"Failed to fetch market {pos.market_id}: {e}")
            continue

        if market.status != MarketStatus.RESOLVED:
            continue

        if pos.dry_run:
            pnl = calculate_dry_run_pnl(pos, market)
            _record_redemption(store, pos, pnl)
        else:
            try:
                success = await adapter.redeem_if_needed(pos.market_id, pos)
                if success:
                    pnl = _calculate_pnl(pos, market)
                    _record_redemption(store, pos, pnl)
                else:
                    logger.warning(f"Redemption failed for {pos.market_id}")
            except PlatformError as e:
                logger.error(f"Redemption error for {pos.market_id}: {e}")
                continue

        if dispatch:
            updated = store.get_position(pos.market_id, pos.asset_id, pos.source_target)
            if updated:
                dispatch("on_redeemed", updated, pnl)


def calculate_dry_run_pnl(pos: OurPosition, market) -> float:
    """Calculate hypothetical P&L for a dry-run position."""
    return _calculate_pnl(pos, market)


def _calculate_pnl(pos: OurPosition, market) -> float:
    """P&L for a resolved position.

    If our outcome matches resolution: profit = size * (1.0 - avg_entry_price)
    If it doesn't: loss = -(size * avg_entry_price)
    """
    if market.resolution_outcome == pos.outcome:
        return pos.size * (1.0 - pos.avg_entry_price)
    else:
        return -(pos.size * pos.avg_entry_price)


def _record_redemption(store, pos: OurPosition, pnl: float) -> None:
    """Zero out position, update realized_pnl, record REDEEM trade."""
    now = datetime.now(timezone.utc)

    # Create a synthetic signal and order for the REDEEM trade record
    target = TargetConfig(
        label=pos.source_target,
        platform=pos.platform,
        address="",
        allocation_pct=0.0,
    )
    signal = Signal(
        signal_type=SignalType.SELL,
        target=target,
        platform=pos.platform,
        market_id=pos.market_id,
        asset_id=pos.asset_id,
        outcome=pos.outcome,
        target_delta=pos.size,
        target_prev_size=pos.size,
        target_price=0.0,
        detected_at=now,
    )
    signal_id = store.insert_signal(signal)

    order = SizedOrder(
        signal=signal,
        side=OrderSide.SELL,
        asset_id=pos.asset_id,
        price=1.0 if pnl >= 0 else 0.0,
        size=pos.size,
        usd_amount=abs(pnl),
        dry_run=pos.dry_run,
    )
    result = OrderResult(
        order=order,
        success=True,
        order_id=None,
        fill_price=order.price,
        fill_size=pos.size,
        error=None,
        executed_at=now,
    )
    store.insert_trade(result, signal_id)

    # Update position: add pnl, zero out
    updated = OurPosition(
        market_id=pos.market_id,
        asset_id=pos.asset_id,
        platform=pos.platform,
        outcome=pos.outcome,
        size=0.0,
        avg_entry_price=pos.avg_entry_price,
        total_cost=0.0,
        realized_pnl=pos.realized_pnl + pnl,
        source_target=pos.source_target,
        dry_run=pos.dry_run,
        updated_at=now,
    )
    store.upsert_position(updated)
    logger.info(f"Redeemed {pos.market_id} ({pos.outcome}): P&L={pnl:+.2f}")
