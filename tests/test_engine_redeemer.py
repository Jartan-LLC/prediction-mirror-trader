from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from prediction_mirror.models.market import Market, MarketStatus
from prediction_mirror.models.position import OurPosition
from prediction_mirror.store import Store, init_db

NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _position(outcome="Yes", size=10.0, avg_entry=0.52, dry_run=True):
    return OurPosition(
        market_id="cond_1",
        asset_id="tok_1",
        platform="polymarket",
        outcome=outcome,
        size=size,
        avg_entry_price=avg_entry,
        total_cost=size * avg_entry,
        realized_pnl=0.0,
        source_target="Whale",
        dry_run=dry_run,
        updated_at=NOW,
    )


def _resolved_market(resolution="Yes"):
    return Market(
        market_id="cond_1",
        platform="polymarket",
        question="Resolved?",
        outcomes=["Yes", "No"],
        status=MarketStatus.RESOLVED,
        resolution_outcome=resolution,
    )


def _open_market():
    return Market(
        market_id="cond_1",
        platform="polymarket",
        question="Still open",
        outcomes=["Yes", "No"],
        status=MarketStatus.OPEN,
    )


@pytest.fixture
def store():
    conn = init_db(":memory:")
    yield Store(conn)
    conn.close()


@pytest.fixture
def mock_adapter():
    adapter = AsyncMock()
    adapter.fetch_market.return_value = _resolved_market("Yes")
    adapter.redeem_if_needed.return_value = True
    return adapter


class TestDryRunPnl:
    def test_winning_outcome(self):
        from prediction_mirror.engine.redeemer import calculate_dry_run_pnl

        pos = _position(outcome="Yes", size=10.0, avg_entry=0.60)
        market = _resolved_market("Yes")
        pnl = calculate_dry_run_pnl(pos, market)
        # profit = 10 * (1.0 - 0.60) = 4.0
        assert pnl == pytest.approx(4.0)

    def test_losing_outcome(self):
        from prediction_mirror.engine.redeemer import calculate_dry_run_pnl

        pos = _position(outcome="No", size=10.0, avg_entry=0.40)
        market = _resolved_market("Yes")
        pnl = calculate_dry_run_pnl(pos, market)
        # loss = -(10 * 0.40) = -4.0
        assert pnl == pytest.approx(-4.0)


class TestRunRedeemerPass:
    @pytest.mark.asyncio
    async def test_dry_run_redemption(self, store, mock_adapter):
        from prediction_mirror.engine.redeemer import run_redeemer_pass

        pos = _position(dry_run=True, outcome="Yes", size=10.0, avg_entry=0.60)
        store.upsert_position(pos)

        await run_redeemer_pass({"polymarket": mock_adapter}, store)

        # Position should be zeroed out
        updated = store.get_position("cond_1", "tok_1", "Whale")
        assert updated.size == 0.0
        assert updated.realized_pnl == pytest.approx(4.0)

    @pytest.mark.asyncio
    async def test_real_redemption(self, store, mock_adapter):
        from prediction_mirror.engine.redeemer import run_redeemer_pass

        pos = _position(dry_run=False, outcome="Yes", size=10.0, avg_entry=0.60)
        store.upsert_position(pos)

        await run_redeemer_pass({"polymarket": mock_adapter}, store)

        mock_adapter.redeem_if_needed.assert_called_once()
        updated = store.get_position("cond_1", "tok_1", "Whale")
        assert updated.size == 0.0

    @pytest.mark.asyncio
    async def test_skips_open_markets(self, store, mock_adapter):
        from prediction_mirror.engine.redeemer import run_redeemer_pass

        mock_adapter.fetch_market.return_value = _open_market()
        pos = _position(dry_run=True, size=10.0)
        store.upsert_position(pos)

        await run_redeemer_pass({"polymarket": mock_adapter}, store)

        # Position unchanged
        updated = store.get_position("cond_1", "tok_1", "Whale")
        assert updated.size == 10.0

    @pytest.mark.asyncio
    async def test_skips_zero_positions(self, store, mock_adapter):
        from prediction_mirror.engine.redeemer import run_redeemer_pass

        pos = _position(dry_run=True, size=0.0)
        store.upsert_position(pos)

        await run_redeemer_pass({"polymarket": mock_adapter}, store)

        # fetch_market should not be called for zero-size positions
        mock_adapter.fetch_market.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatches_on_redeemed(self, store, mock_adapter):
        from prediction_mirror.engine.redeemer import run_redeemer_pass

        pos = _position(dry_run=True, outcome="Yes", size=10.0, avg_entry=0.60)
        store.upsert_position(pos)

        events = []
        def dispatch(event, *args):
            events.append((event, args))

        await run_redeemer_pass({"polymarket": mock_adapter}, store, dispatch=dispatch)

        redeemed = [e for e in events if e[0] == "on_redeemed"]
        assert len(redeemed) == 1
