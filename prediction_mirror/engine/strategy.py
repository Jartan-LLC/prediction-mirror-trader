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


def _slippage_pct(signal_price: float, current_price: float) -> float:
    if signal_price <= 0:
        return 0.0
    return abs(current_price - signal_price) / signal_price * 100


def percentile_rank(value: float, history: list[float]) -> float:
    """0.0 to 1.0 — fraction of history values <= this value."""
    count_below = sum(1 for v in history if v <= value)
    return count_below / len(history)


def size_order(
    signal: Signal,
    current_price: float,
    portfolio_value: float,
    target_portfolio_value: float,
    deployed_for_target: float,
    our_position: OurPosition | None,
    settings: Settings,
    trade_history: list[float] | None = None,
) -> tuple[SizedOrder | None, str | None]:
    """Pure calculation. Returns (SizedOrder, None) or (None, reason)."""
    dry_run = settings.dry_run

    if signal.signal_type == SignalType.SELL:
        return _size_sell(signal, current_price, our_position, settings, dry_run)

    target = signal.target
    if target.sizing_mode == "conviction":
        return _size_buy_conviction(
            signal, current_price, portfolio_value, deployed_for_target,
            our_position, settings, dry_run, trade_history or [],
        )

    return _size_buy_proportional(
        signal, current_price, portfolio_value, target_portfolio_value,
        deployed_for_target, our_position, settings, dry_run,
    )


# ── Conviction-based buy sizing ──


def _size_buy_conviction(
    signal: Signal,
    current_price: float,
    portfolio_value: float,
    deployed_for_target: float,
    our_position: OurPosition | None,
    settings: Settings,
    dry_run: bool,
    trade_history: list[float],
) -> tuple[SizedOrder | None, str | None]:
    target = signal.target
    target_budget = portfolio_value * (target.allocation_pct / 100)
    available = target_budget - deployed_for_target

    if available <= 0:
        return None, f"no budget available (budget=${target_budget:.2f}, deployed=${deployed_for_target:.2f})"

    # This trade's USD value
    trade_usd = signal.target_delta * current_price

    # Determine budget fraction based on conviction
    if len(trade_history) < target.min_history:
        # Cold start — use fixed fraction
        fraction = target.cold_start_pct / 100
        sizing_detail = (
            f"cold start ({len(trade_history)}/{target.min_history} trades, "
            f"using {target.cold_start_pct:.0f}%)"
        )
    else:
        pct_rank = percentile_rank(trade_usd, trade_history)
        floor = target.conviction_floor_pct / 100
        ceiling = target.conviction_ceiling_pct / 100
        fraction = floor + pct_rank * (ceiling - floor)
        sizing_detail = (
            f"P{pct_rank * 100:.0f} conviction "
            f"→ {fraction * 100:.0f}% of available"
        )

    usd_amount = available * fraction * target.multiplier

    # Cap at max_order_usd
    if usd_amount > settings.max_order_usd:
        usd_amount = settings.max_order_usd

    # Cap at max_position_usd
    existing_cost = our_position.total_cost if our_position else 0.0
    position_room = settings.max_position_usd - existing_cost
    if position_room <= 0:
        return None, f"max position reached (${existing_cost:.2f}/${settings.max_position_usd:.2f})"
    if usd_amount > position_room:
        usd_amount = position_room

    # Convert to shares
    raw_size = usd_amount / current_price if current_price > 0 else 0

    # Skip if below minimum
    if usd_amount < settings.min_order_usd:
        return None, (
            f"below minimum order (${usd_amount:.4f} < "
            f"${settings.min_order_usd:.2f}, {sizing_detail})"
        )

    # Slippage check
    if not check_slippage(signal.target_price, current_price, settings.slippage_tolerance_pct):
        slip = _slippage_pct(signal.target_price, current_price)
        return None, (
            f"slippage {slip:.1f}% exceeds {settings.slippage_tolerance_pct:.1f}% tolerance "
            f"(signal=${signal.target_price:.3f}, current=${current_price:.3f})"
        )

    return SizedOrder(
        signal=signal,
        side=OrderSide.BUY,
        asset_id=signal.asset_id,
        price=current_price,
        size=raw_size,
        usd_amount=usd_amount,
        dry_run=dry_run,
    ), None


# ── Proportional buy sizing (legacy) ──


def _size_buy_proportional(
    signal: Signal,
    current_price: float,
    portfolio_value: float,
    target_portfolio_value: float,
    deployed_for_target: float,
    our_position: OurPosition | None,
    settings: Settings,
    dry_run: bool,
) -> tuple[SizedOrder | None, str | None]:
    target = signal.target
    target_budget = portfolio_value * (target.allocation_pct / 100)
    available = target_budget - deployed_for_target

    if available <= 0:
        return None, (
            f"no budget available (budget=${target_budget:.2f}, "
            f"deployed=${deployed_for_target:.2f})"
        )

    if target_portfolio_value <= 0:
        return None, "target portfolio value is zero"

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

    # Cap at max_position_usd
    existing_cost = our_position.total_cost if our_position else 0.0
    position_room = settings.max_position_usd - existing_cost
    if position_room <= 0:
        return None, f"max position reached (${existing_cost:.2f}/${settings.max_position_usd:.2f})"
    if usd_amount > position_room:
        usd_amount = position_room
        raw_size = usd_amount / current_price if current_price > 0 else 0

    # Skip if below minimum
    if usd_amount < settings.min_order_usd:
        return None, f"below minimum order (${usd_amount:.4f} < ${settings.min_order_usd:.2f})"

    # Slippage check
    if not check_slippage(signal.target_price, current_price, settings.slippage_tolerance_pct):
        slip = _slippage_pct(signal.target_price, current_price)
        return None, (
            f"slippage {slip:.1f}% exceeds {settings.slippage_tolerance_pct:.1f}% tolerance "
            f"(signal=${signal.target_price:.3f}, current=${current_price:.3f})"
        )

    return SizedOrder(
        signal=signal,
        side=OrderSide.BUY,
        asset_id=signal.asset_id,
        price=current_price,
        size=raw_size,
        usd_amount=usd_amount,
        dry_run=dry_run,
    ), None


# ── Sell sizing (unchanged — percentage mirror) ──


def _size_sell(
    signal: Signal,
    current_price: float,
    our_position: OurPosition | None,
    settings: Settings,
    dry_run: bool,
) -> tuple[SizedOrder | None, str | None]:
    if our_position is None or our_position.size <= 0:
        return None, "no position to sell"

    # Full exit: target_prev_size == delta means they sold everything
    if signal.target_prev_size > 0 and abs(signal.target_delta - signal.target_prev_size) < 0.001:
        raw_size = our_position.size
    else:
        if signal.target_prev_size <= 0:
            return None, "target_prev_size is zero"
        reduction_pct = signal.target_delta / signal.target_prev_size
        raw_size = our_position.size * reduction_pct

    # Cap at our actual holding
    raw_size = min(raw_size, our_position.size)
    usd_amount = raw_size * current_price

    # Skip if below minimum
    if usd_amount < settings.min_order_usd:
        return None, f"below minimum order (${usd_amount:.4f} < ${settings.min_order_usd:.2f})"

    # Slippage check
    if not check_slippage(signal.target_price, current_price, settings.slippage_tolerance_pct):
        slip = _slippage_pct(signal.target_price, current_price)
        return None, (
            f"slippage {slip:.1f}% exceeds {settings.slippage_tolerance_pct:.1f}% tolerance "
            f"(signal=${signal.target_price:.3f}, current=${current_price:.3f})"
        )

    return SizedOrder(
        signal=signal,
        side=OrderSide.SELL,
        asset_id=signal.asset_id,
        price=current_price,
        size=raw_size,
        usd_amount=usd_amount,
        dry_run=dry_run,
    ), None
