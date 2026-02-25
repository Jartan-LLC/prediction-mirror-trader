from __future__ import annotations

from datetime import datetime, timezone

import pytest

from prediction_mirror.models.order import OrderResult, OrderSide, SizedOrder
from prediction_mirror.models.position import OurPosition
from prediction_mirror.models.signal import Signal, SignalType
from prediction_mirror.models.target import TargetConfig
from prediction_mirror.store import Store, init_db

NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def store():
    conn = init_db(":memory:")
    yield Store(conn)
    conn.close()


def _make_position(
    market_id="cond_1",
    asset_id="tok_1",
    source_target="Whale",
    size=15.0,
    dry_run=False,
    **kw,
):
    defaults = dict(
        market_id=market_id,
        asset_id=asset_id,
        platform="polymarket",
        outcome="Yes",
        size=size,
        avg_entry_price=0.52,
        total_cost=size * 0.52,
        realized_pnl=0.0,
        source_target=source_target,
        dry_run=dry_run,
        updated_at=NOW,
    )
    defaults.update(kw)
    return OurPosition(**defaults)


class TestUpsertPosition:
    def test_insert_and_get(self, store: Store):
        pos = _make_position()
        store.upsert_position(pos)
        result = store.get_position("cond_1", "tok_1", "Whale")
        assert result is not None
        assert result.size == 15.0

    def test_upsert_updates(self, store: Store):
        store.upsert_position(_make_position(size=15.0))
        store.upsert_position(_make_position(size=25.0))
        result = store.get_position("cond_1", "tok_1", "Whale")
        assert result.size == 25.0

    def test_get_position_not_found(self, store: Store):
        assert store.get_position("x", "y", "z") is None


class TestGetPositions:
    def test_get_all(self, store: Store):
        store.upsert_position(_make_position(market_id="c1", asset_id="t1"))
        store.upsert_position(_make_position(market_id="c2", asset_id="t2"))
        assert len(store.get_all_positions()) == 2

    def test_filter_by_dry_run(self, store: Store):
        store.upsert_position(_make_position(market_id="c1", asset_id="t1", dry_run=False))
        store.upsert_position(_make_position(market_id="c2", asset_id="t2", dry_run=True))
        real = store.get_all_positions(dry_run=False)
        paper = store.get_all_positions(dry_run=True)
        assert len(real) == 1
        assert len(paper) == 1
        assert not real[0].dry_run
        assert paper[0].dry_run

    def test_get_by_target(self, store: Store):
        store.upsert_position(_make_position(source_target="Whale", market_id="c1", asset_id="t1"))
        store.upsert_position(_make_position(source_target="Degen", market_id="c2", asset_id="t2"))
        whale_pos = store.get_positions_by_target("Whale")
        assert len(whale_pos) == 1
        assert whale_pos[0].source_target == "Whale"


class TestZeroOut:
    def test_zero_out(self, store: Store):
        store.upsert_position(_make_position(size=15.0))
        store.zero_out_position("cond_1", "tok_1", "Whale")
        result = store.get_position("cond_1", "tok_1", "Whale")
        assert result.size == 0
        assert result.total_cost == 0


class TestDeployed:
    def test_deployed_for_target(self, store: Store):
        store.upsert_position(_make_position(source_target="Whale", size=10.0, dry_run=False))
        deployed = store.get_deployed_for_target("Whale")
        assert deployed == pytest.approx(10.0 * 0.52)

    def test_deployed_filters_by_dry_run(self, store: Store):
        store.upsert_position(_make_position(source_target="Whale", size=10.0, dry_run=True))
        assert store.get_deployed_for_target("Whale", dry_run=False) == 0.0
        assert store.get_deployed_for_target("Whale", dry_run=True) == pytest.approx(10.0 * 0.52)
        # No filter returns all
        assert store.get_deployed_for_target("Whale") == pytest.approx(10.0 * 0.52)

    def test_deployed_excludes_zero_size(self, store: Store):
        store.upsert_position(_make_position(source_target="Whale", size=0.0, dry_run=False))
        deployed = store.get_deployed_for_target("Whale")
        assert deployed == 0.0

    def test_total_deployed(self, store: Store):
        store.upsert_position(
            _make_position(source_target="A", market_id="c1", asset_id="t1", size=10.0)
        )
        store.upsert_position(
            _make_position(source_target="B", market_id="c2", asset_id="t2", size=5.0)
        )
        total = store.get_total_deployed()
        assert total == pytest.approx(10.0 * 0.52 + 5.0 * 0.52)


class TestSignalsAndTrades:
    """Test signal/trade round-trips through the Store facade."""

    def _make_signal(self):
        target = TargetConfig(
            label="Whale", platform="polymarket", address="0xAAA", allocation_pct=50.0
        )
        return Signal(
            signal_type=SignalType.BUY,
            target=target,
            platform="polymarket",
            market_id="cond_1",
            asset_id="tok_1",
            outcome="Yes",
            target_delta=10.0,
            target_prev_size=90.0,
            target_price=0.55,
            detected_at=NOW,
        )

    def test_insert_signal(self, store: Store):
        signal = self._make_signal()
        signal_id = store.insert_signal(signal)
        assert signal_id > 0

    def test_signal_history(self, store: Store):
        signal = self._make_signal()
        store.insert_signal(signal)
        history = store.get_signal_history(limit=10)
        assert len(history) == 1
        assert history[0]["signal_type"] == "BUY"

    def test_insert_trade(self, store: Store):
        signal = self._make_signal()
        signal_id = store.insert_signal(signal)
        order = SizedOrder(
            signal=signal,
            side=OrderSide.BUY,
            asset_id="tok_1",
            price=0.55,
            size=5.0,
            usd_amount=2.75,
            dry_run=True,
        )
        result = OrderResult(
            order=order,
            success=True,
            order_id="ord_1",
            fill_price=0.55,
            fill_size=5.0,
            error=None,
            executed_at=NOW,
        )
        trade_id = store.insert_trade(result, signal_id)
        assert trade_id > 0

    def test_trade_summary(self, store: Store):
        summary = store.get_trade_summary()
        assert summary["total_trades"] == 0

    def test_atomic_trade_and_position(self, store: Store):
        """Trade + position update in a transaction."""
        signal = self._make_signal()
        signal_id = store.insert_signal(signal)
        order = SizedOrder(
            signal=signal,
            side=OrderSide.BUY,
            asset_id="tok_1",
            price=0.55,
            size=5.0,
            usd_amount=2.75,
            dry_run=True,
        )
        result = OrderResult(
            order=order,
            success=True,
            order_id="ord_1",
            fill_price=0.55,
            fill_size=5.0,
            error=None,
            executed_at=NOW,
        )
        pos = _make_position(size=5.0, dry_run=True)

        # Atomic: insert trade + upsert position
        with store.conn:
            from prediction_mirror.store import trades, portfolio
            trades.insert_trade(store.conn, result, signal_id)
            portfolio.upsert_position(store.conn, pos)

        assert store.get_position("cond_1", "tok_1", "Whale") is not None
        assert len(store.get_recent_trades()) == 1
