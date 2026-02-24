from __future__ import annotations

from prediction_mirror.models.order import OrderSide, SizedOrder
from prediction_mirror.models.position import OurPosition
from prediction_mirror.models.settings import Settings
from prediction_mirror.models.signal import Signal, SignalType


def check_slippage(signal_price: float, current_price: float, tolerance_pct: float) -> bool:
    """Returns True if slippage is acceptable."""
    if signal_price <= 0:
        return True
    slippage_pct = abs(current_price - signal_price) / signal_price * 100
    return slippage_pct <= tolerance_pct


def size_order(
    signal: Signal,
    current_price: float,
    portfolio_value: float,
    target_portfolio_value: float,
    deployed_for_target: float,
    our_position: OurPosition | None,
    settings: Settings,
) -> SizedOrder | None:
    """Pure calculation. Returns a SizedOrder or None if the order should be skipped."""
    dry_run = settings.dry_run

    if signal.signal_type == SignalType.SELL:
        return _size_sell(signal, current_price, our_position, settings, dry_run)

    return _size_buy(
        signal, current_price, portfolio_value, target_portfolio_value,
        deployed_for_target, our_position, settings, dry_run,
    )


def _size_buy(
    signal: Signal,
    current_price: float,
    portfolio_value: float,
    target_portfolio_value: float,
    deployed_for_target: float,
    our_position: OurPosition | None,
    settings: Settings,
    dry_run: bool,
) -> SizedOrder | None:
    target = signal.target
    target_budget = portfolio_value * (target.allocation_pct / 100)
    available = target_budget - deployed_for_target

    if available <= 0:
        return None

    if target_portfolio_value <= 0:
        return None

    ratio = target_budget / target_portfolio_value
    raw_size = signal.target_delta * ratio * target.multiplier
    usd_amount = raw_size * current_price

    # Cap at available budget
    if usd_amount > available:
        usd_amount = available
        raw_size = usd_amount / current_price if current_price > 0 else 0

    # Cap at max_order_usd
    if usd_amount > settings.max_order_usd:
        usd_amount = settings.max_order_usd
        raw_size = usd_amount / current_price if current_price > 0 else 0

    # Cap at max_position_usd (considering existing holding)
    existing_cost = our_position.total_cost if our_position else 0.0
    position_room = settings.max_position_usd - existing_cost
    if position_room <= 0:
        return None
    if usd_amount > position_room:
        usd_amount = position_room
        raw_size = usd_amount / current_price if current_price > 0 else 0

    # Skip if below minimum
    if usd_amount < settings.min_order_usd:
        return None

    # Slippage check
    if not check_slippage(signal.target_price, current_price, settings.slippage_tolerance_pct):
        return None

    return SizedOrder(
        signal=signal,
        side=OrderSide.BUY,
        asset_id=signal.asset_id,
        price=current_price,
        size=raw_size,
        usd_amount=usd_amount,
        dry_run=dry_run,
    )


def _size_sell(
    signal: Signal,
    current_price: float,
    our_position: OurPosition | None,
    settings: Settings,
    dry_run: bool,
) -> SizedOrder | None:
    if our_position is None or our_position.size <= 0:
        return None

    # Full exit: target_prev_size == delta means they sold everything
    if signal.target_prev_size > 0 and abs(signal.target_delta - signal.target_prev_size) < 0.001:
        raw_size = our_position.size
    else:
        if signal.target_prev_size <= 0:
            return None
        reduction_pct = signal.target_delta / signal.target_prev_size
        raw_size = our_position.size * reduction_pct

    # Cap at our actual holding
    raw_size = min(raw_size, our_position.size)
    usd_amount = raw_size * current_price

    # Skip if below minimum
    if usd_amount < settings.min_order_usd:
        return None

    # Slippage check
    if not check_slippage(signal.target_price, current_price, settings.slippage_tolerance_pct):
        return None

    return SizedOrder(
        signal=signal,
        side=OrderSide.SELL,
        asset_id=signal.asset_id,
        price=current_price,
        size=raw_size,
        usd_amount=usd_amount,
        dry_run=dry_run,
    )
