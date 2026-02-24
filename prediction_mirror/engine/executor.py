from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from prediction_mirror.models.order import OrderResult, OrderSide, SizedOrder
from prediction_mirror.models.position import OurPosition
from prediction_mirror.models.settings import Settings
from prediction_mirror.models.signal import Signal, SignalType
from prediction_mirror.engine.strategy import size_order
from prediction_mirror.platforms.base import PlatformAdapter
from prediction_mirror.platforms.errors import FatalError, TransientError

logger = logging.getLogger(__name__)

MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF = [1, 2, 4]  # seconds


async def handle_signals(
    signals: list[Signal],
    adapter: PlatformAdapter,
    store,
    settings: Settings,
    dispatch=None,
    track_goals: bool = True,
) -> list[OrderResult]:
    """Process signals: size, execute (or paper-trade), persist."""
    results = []
    for signal in signals:
        result = await _process_signal(
            signal, adapter, store, settings, dispatch, track_goals,
        )
        if result is not None:
            results.append(result)
    return results


async def _process_signal(
    signal: Signal,
    adapter: PlatformAdapter,
    store,
    settings: Settings,
    dispatch=None,
    track_goals: bool = True,
) -> OrderResult | None:
    """Process a single signal end-to-end."""
    # Persist signal to audit log (skip for reconciliation retries)
    if track_goals:
        signal_id = store.insert_signal(signal)
        if dispatch:
            dispatch("on_signal", signal)
    else:
        signal_id = 0

    # Gather context for sizing
    target_pv = 0.0
    if signal.target.sizing_mode == "proportional":
        try:
            target_pv = await adapter.fetch_target_portfolio_value(signal.target.address)
        except Exception as e:
            logger.warning(f"Failed to get target portfolio value: {e}")
            return None

    deployed = store.get_deployed_for_target(
        signal.target.label, dry_run=settings.dry_run
    )
    our_pos = store.get_position(signal.market_id, signal.asset_id, signal.target.label)

    # Calculate portfolio value
    if settings.dry_run:
        cash = settings.dry_run_cash
        if cash < 0:
            cash = settings.dry_run_balance_usd
        portfolio_value = cash + store.get_total_deployed(dry_run=True)
    else:
        try:
            wallet = await adapter.get_wallet_state()
        except Exception as e:
            logger.warning(f"Failed to get wallet state: {e}")
            return None
        portfolio_value = (
            wallet.total_balance + store.get_total_deployed(dry_run=False)
        )

    # Get current price for sizing
    try:
        side = "buy" if signal.signal_type == SignalType.BUY else "sell"
        current_price = await adapter.get_price(signal.asset_id, side)
    except Exception as e:
        logger.warning(f"Failed to get price for {signal.asset_id}: {e}")
        return None

    # Get trade history for conviction sizing
    trade_history = store.get_trade_history(
        signal.target.label, signal.target.history_window
    )

    # For sells, fetch target's current position to calculate reduction %
    target_current_size = None
    if signal.signal_type == SignalType.SELL:
        try:
            target_positions = await adapter.fetch_target_positions(
                signal.target.address
            )
            for tp in target_positions:
                if tp.asset_id == signal.asset_id:
                    target_current_size = tp.size
                    break
            if target_current_size is None:
                target_current_size = 0.0  # fully exited
        except Exception as e:
            logger.warning(f"Failed to fetch target positions for sell sizing: {e}")

    # Size the order
    sized, skip_reason, retriable = size_order(
        signal=signal,
        current_price=current_price,
        portfolio_value=portfolio_value,
        target_portfolio_value=target_pv,
        deployed_for_target=deployed,
        our_position=our_pos,
        settings=settings,
        trade_history=trade_history,
        target_current_size=target_current_size,
    )

    if sized is None:
        logger.info(
            f"Skipped {signal.signal_type.value} {signal.target.label} "
            f"{signal.outcome}@{signal.market_id[:12]}.. — {skip_reason}"
        )
        if retriable and track_goals and signal.signal_type == SignalType.SELL:
            store.upsert_goal(
                signal.target.label, signal.market_id, signal.asset_id,
                signal.outcome, signal.platform, -signal.target_delta,
                signal.target_price,
            )
        return None

    # Execute
    if sized.dry_run:
        result = _paper_trade(sized)
    else:
        result = await _execute_with_retry(sized, adapter)

    if result.success:
        filled = result.fill_size or 0
        # Reduce any pending goal for this asset
        store.reduce_goal(
            signal.target.label, signal.market_id, signal.asset_id, filled,
        )
        # Check for partial fill — unfilled sell remainder becomes a goal
        if (track_goals and sized.side == OrderSide.SELL
                and filled < sized.size):
            remainder = sized.size - filled
            store.upsert_goal(
                signal.target.label, signal.market_id, signal.asset_id,
                signal.outcome, signal.platform, -remainder, current_price,
            )
    elif track_goals and sized.side == OrderSide.SELL:
        # Sell execution failed — create goal
        store.upsert_goal(
            signal.target.label, signal.market_id, signal.asset_id,
            signal.outcome, signal.platform, -sized.size, current_price,
        )

    # Persist atomically
    _persist_result(store, result, signal_id, our_pos)

    if dispatch:
        dispatch("on_trade", result)
        pos = store.get_position(signal.market_id, signal.asset_id, signal.target.label)
        if pos:
            dispatch("on_position_update", pos)

    return result


def _paper_trade(order: SizedOrder) -> OrderResult:
    """Simulate execution for dry-run mode."""
    return OrderResult(
        order=order,
        success=True,
        order_id=None,
        fill_price=order.price,
        fill_size=order.size,
        error=None,
        executed_at=datetime.now(timezone.utc),
    )


async def _execute_with_retry(
    order: SizedOrder, adapter: PlatformAdapter
) -> OrderResult:
    """Submit order with exponential backoff retry on transient errors."""
    last_error = None
    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            return await adapter.submit_order(order)
        except TransientError as e:
            last_error = str(e)
            logger.warning(
                f"Transient error (attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS}): {e}"
            )
            if attempt < MAX_RETRY_ATTEMPTS - 1:
                await asyncio.sleep(RETRY_BACKOFF[attempt])
        except FatalError as e:
            logger.error(f"Fatal error submitting order: {e}")
            return OrderResult(
                order=order,
                success=False,
                order_id=None,
                fill_price=None,
                fill_size=None,
                error=str(e),
                executed_at=datetime.now(timezone.utc),
            )

    # All retries exhausted
    return OrderResult(
        order=order,
        success=False,
        order_id=None,
        fill_price=None,
        fill_size=None,
        error=f"Max retries exceeded: {last_error}",
        executed_at=datetime.now(timezone.utc),
    )


def _persist_result(store, result: OrderResult, signal_id: int, old_position: OurPosition | None):
    """Atomically persist trade + update position + update dry-run cash."""
    order = result.order
    now = datetime.now(timezone.utc)

    with store.conn:
        from prediction_mirror.store import trades, portfolio, settings

        trades.insert_trade(store.conn, result, signal_id)

        if result.success and result.fill_size and result.fill_price:
            # Update dry-run cash balance
            if order.dry_run:
                trade_usd = result.fill_size * result.fill_price
                current = settings.get_current(store.conn)
                cash = current.dry_run_cash
                if cash < 0:
                    cash = current.dry_run_balance_usd
                if order.side == OrderSide.BUY:
                    cash -= trade_usd
                elif order.side == OrderSide.SELL:
                    cash += trade_usd
                settings.set_value(store.conn, "dry_run_cash", str(cash))

            if order.side == OrderSide.BUY:
                old_size = old_position.size if old_position else 0.0
                old_cost = old_position.total_cost if old_position else 0.0
                old_pnl = old_position.realized_pnl if old_position else 0.0

                new_size = old_size + result.fill_size
                new_cost = old_cost + (result.fill_size * result.fill_price)
                new_avg = new_cost / new_size if new_size > 0 else 0.0

                pos = OurPosition(
                    market_id=order.signal.market_id,
                    asset_id=order.asset_id,
                    platform=order.signal.platform,
                    outcome=order.signal.outcome,
                    size=new_size,
                    avg_entry_price=new_avg,
                    total_cost=new_cost,
                    realized_pnl=old_pnl,
                    source_target=order.signal.target.label,
                    dry_run=order.dry_run,
                    updated_at=now,
                )
                portfolio.upsert_position(store.conn, pos)

            elif order.side == OrderSide.SELL:
                old_size = old_position.size if old_position else 0.0
                old_avg = old_position.avg_entry_price if old_position else 0.0
                old_pnl = old_position.realized_pnl if old_position else 0.0

                new_size = old_size - result.fill_size
                new_cost = new_size * old_avg

                pos = OurPosition(
                    market_id=order.signal.market_id,
                    asset_id=order.asset_id,
                    platform=order.signal.platform,
                    outcome=order.signal.outcome,
                    size=max(new_size, 0.0),
                    avg_entry_price=old_avg,
                    total_cost=max(new_cost, 0.0),
                    realized_pnl=old_pnl,
                    source_target=order.signal.target.label,
                    dry_run=order.dry_run,
                    updated_at=now,
                )
                portfolio.upsert_position(store.conn, pos)
