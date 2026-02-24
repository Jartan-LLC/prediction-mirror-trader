from __future__ import annotations

from prediction_mirror.models.order import OrderSide, SizedOrder
from prediction_mirror.models.position import OurPosition
from prediction_mirror.models.settings import Settings
from prediction_mirror.models.signal import Signal, SignalType

# Return type: (order_or_None, reason_or_None, retriable)
SizeResult = tuple[SizedOrder | None, str | None, bool]


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


def _skip(reason: str, retriable: bool = False) -> SizeResult:
    return None, reason, retriable


def _success(order: SizedOrder) -> SizeResult:
    return order, None, False


def size_order(
    signal: Signal,
    current_price: float,
    portfolio_value: float,
    target_portfolio_value: float,
    deployed_for_target: float,
    our_position: OurPosition | None,
    settings: Settings,
    trade_history: list[float] | None = None,
    target_current_size: float | None = None,
) -> SizeResult:
    """Pure calculation. Returns (SizedOrder, None, False) or (None, reason, retriable)."""
    dry_run = settings.dry_run

    if signal.signal_type == SignalType.SELL:
        return _size_sell(
            signal, current_price, our_position, settings, dry_run,
            trade_history, target_current_size,
        )

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
) -> SizeResult:
    target = signal.target
    target_budget = portfolio_value * (target.allocation_pct / 100)
    available = target_budget - deployed_for_target

    if available <= 0:
        return _skip(
            f"no budget available (budget=${target_budget:.2f}, "
            f"deployed=${deployed_for_target:.2f})",
            retriable=True,
        )

    trade_usd = signal.target_delta * current_price
    base = target.trade_size_pct / 100

    if len(trade_history) < target.min_history:
        fraction = target.cold_start_pct / 100
        sizing_detail = (
            f"cold start ({len(trade_history)}/{target.min_history} trades, "
            f"using {target.cold_start_pct:.0f}%)"
        )
        if fraction <= 0:
            return _skip(sizing_detail, retriable=False)
    else:
        pct_rank = percentile_rank(trade_usd, trade_history)
        fraction = base * (1 + pct_rank)
        sizing_detail = (
            f"P{pct_rank * 100:.0f} conviction "
            f"→ {fraction * 100:.1f}% of available"
        )

    usd_amount = available * fraction * target.multiplier

    if usd_amount > settings.max_order_usd:
        usd_amount = settings.max_order_usd

    existing_cost = our_position.total_cost if our_position else 0.0
    position_room = settings.max_position_usd - existing_cost
    if position_room <= 0:
        return _skip(
            f"max position reached "
            f"(${existing_cost:.2f}/${settings.max_position_usd:.2f})",
            retriable=False,
        )
    if usd_amount > position_room:
        usd_amount = position_room

    raw_size = usd_amount / current_price if current_price > 0 else 0

    if usd_amount < settings.min_order_usd:
        return _skip(
            f"below minimum order (${usd_amount:.4f} < "
            f"${settings.min_order_usd:.2f}, {sizing_detail})",
            retriable=False,
        )

    if not check_slippage(
        signal.target_price, current_price, settings.slippage_tolerance_pct
    ):
        slip = _slippage_pct(signal.target_price, current_price)
        return _skip(
            f"slippage {slip:.1f}% exceeds "
            f"{settings.slippage_tolerance_pct:.1f}% tolerance "
            f"(signal=${signal.target_price:.3f}, "
            f"current=${current_price:.3f})",
            retriable=True,
        )

    return _success(SizedOrder(
        signal=signal,
        side=OrderSide.BUY,
        asset_id=signal.asset_id,
        price=current_price,
        size=raw_size,
        usd_amount=usd_amount,
        dry_run=dry_run,
    ))


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
) -> SizeResult:
    target = signal.target
    target_budget = portfolio_value * (target.allocation_pct / 100)
    available = target_budget - deployed_for_target

    if available <= 0:
        return _skip(
            f"no budget available (budget=${target_budget:.2f}, "
            f"deployed=${deployed_for_target:.2f})",
            retriable=True,
        )

    if target_portfolio_value <= 0:
        return _skip("target portfolio value is zero", retriable=False)

    ratio = target_budget / target_portfolio_value
    raw_size = signal.target_delta * ratio * target.multiplier
    usd_amount = raw_size * current_price

    if usd_amount > available:
        usd_amount = available
        raw_size = usd_amount / current_price if current_price > 0 else 0

    if usd_amount > settings.max_order_usd:
        usd_amount = settings.max_order_usd
        raw_size = usd_amount / current_price if current_price > 0 else 0

    existing_cost = our_position.total_cost if our_position else 0.0
    position_room = settings.max_position_usd - existing_cost
    if position_room <= 0:
        return _skip(
            f"max position reached "
            f"(${existing_cost:.2f}/${settings.max_position_usd:.2f})",
            retriable=False,
        )
    if usd_amount > position_room:
        usd_amount = position_room
        raw_size = usd_amount / current_price if current_price > 0 else 0

    if usd_amount < settings.min_order_usd:
        return _skip(
            f"below minimum order "
            f"(${usd_amount:.4f} < ${settings.min_order_usd:.2f})",
            retriable=False,
        )

    if not check_slippage(
        signal.target_price, current_price, settings.slippage_tolerance_pct
    ):
        slip = _slippage_pct(signal.target_price, current_price)
        return _skip(
            f"slippage {slip:.1f}% exceeds "
            f"{settings.slippage_tolerance_pct:.1f}% tolerance "
            f"(signal=${signal.target_price:.3f}, "
            f"current=${current_price:.3f})",
            retriable=True,
        )

    return _success(SizedOrder(
        signal=signal,
        side=OrderSide.BUY,
        asset_id=signal.asset_id,
        price=current_price,
        size=raw_size,
        usd_amount=usd_amount,
        dry_run=dry_run,
    ))


# ── Sell sizing ──


def _size_sell(
    signal: Signal,
    current_price: float,
    our_position: OurPosition | None,
    settings: Settings,
    dry_run: bool,
    trade_history: list[float] | None = None,
    target_current_size: float | None = None,
) -> SizeResult:
    if our_position is None or our_position.size <= 0:
        return _skip("no position to sell", retriable=False)

    if target_current_size is not None:
        prev_size = target_current_size + signal.target_delta
        if prev_size <= 0:
            reduction_pct = 1.0
        else:
            reduction_pct = signal.target_delta / prev_size
        raw_size = our_position.size * reduction_pct
        sizing_detail = (
            f"target reduced {reduction_pct * 100:.0f}% "
            f"({signal.target_delta:.0f}/{prev_size:.0f})"
        )
    elif signal.target_prev_size > 0:
        reduction_pct = signal.target_delta / signal.target_prev_size
        raw_size = our_position.size * reduction_pct
        sizing_detail = "proportional"
    else:
        raw_size = our_position.size * (signal.target.trade_size_pct / 100)
        sizing_detail = "no target size info, using trade_size_pct"

    raw_size = min(raw_size, our_position.size)
    usd_amount = raw_size * current_price

    if usd_amount < settings.min_order_usd:
        return _skip(
            f"below minimum order (${usd_amount:.4f} < "
            f"${settings.min_order_usd:.2f}, {sizing_detail})",
            retriable=False,
        )

    if not check_slippage(
        signal.target_price, current_price, settings.slippage_tolerance_pct
    ):
        slip = _slippage_pct(signal.target_price, current_price)
        return _skip(
            f"slippage {slip:.1f}% exceeds "
            f"{settings.slippage_tolerance_pct:.1f}% tolerance "
            f"(signal=${signal.target_price:.3f}, "
            f"current=${current_price:.3f})",
            retriable=True,
        )

    return _success(SizedOrder(
        signal=signal,
        side=OrderSide.SELL,
        asset_id=signal.asset_id,
        price=current_price,
        size=raw_size,
        usd_amount=usd_amount,
        dry_run=dry_run,
    ))
