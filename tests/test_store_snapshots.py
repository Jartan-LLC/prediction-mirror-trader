from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from prediction_mirror.models.position import TargetPosition
from prediction_mirror.store import Store, init_db

NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def store():
    conn = init_db(":memory:")
    yield Store(conn)
    conn.close()


def _make_snapshot(
    target_address="0xAAA",
    market_id="cond_1",
    asset_id="tok_1",
    size=100.0,
    **kw,
):
    defaults = dict(
        target_address=target_address,
        platform="polymarket",
        market_id=market_id,
        asset_id=asset_id,
        outcome="Yes",
        size=size,
        avg_price=0.55,
        current_price=0.60,
        snapshot_time=NOW,
    )
    defaults.update(kw)
    return TargetPosition(**defaults)


class TestUpsertSnapshot:
    def test_insert_and_retrieve(self, store: Store):
        snap = _make_snapshot()
        store.upsert_snapshot(snap)
        result = store.get_snapshot("0xAAA", "polymarket", "cond_1", "tok_1")
        assert result is not None
        assert result.size == 100.0
        assert result.avg_price == 0.55

    def test_upsert_updates_existing(self, store: Store):
        store.upsert_snapshot(_make_snapshot(size=100.0))
        store.upsert_snapshot(_make_snapshot(size=150.0))
        result = store.get_snapshot("0xAAA", "polymarket", "cond_1", "tok_1")
        assert result.size == 150.0

    def test_get_snapshot_not_found(self, store: Store):
        result = store.get_snapshot("0xZZZ", "poly", "cond_x", "tok_x")
        assert result is None


class TestGetAllSnapshots:
    def test_multiple_snapshots(self, store: Store):
        store.upsert_snapshot(_make_snapshot(market_id="cond_1", asset_id="tok_1"))
        store.upsert_snapshot(_make_snapshot(market_id="cond_2", asset_id="tok_2"))
        results = store.get_all_snapshots("0xAAA")
        assert len(results) == 2

    def test_filters_by_address(self, store: Store):
        store.upsert_snapshot(_make_snapshot(target_address="0xAAA"))
        store.upsert_snapshot(_make_snapshot(target_address="0xBBB"))
        results = store.get_all_snapshots("0xAAA")
        assert len(results) == 1
        assert results[0].target_address == "0xAAA"


class TestDeleteStaleSnapshots:
    def test_deletes_old_snapshots(self, store: Store):
        old = _make_snapshot(snapshot_time=NOW - timedelta(hours=2))
        recent = _make_snapshot(
            market_id="cond_2",
            asset_id="tok_2",
            snapshot_time=NOW,
        )
        store.upsert_snapshot(old)
        store.upsert_snapshot(recent)

        from prediction_mirror.store.snapshots import delete_stale_snapshots
        deleted = delete_stale_snapshots(store.conn, NOW - timedelta(hours=1))
        assert deleted == 1

        results = store.get_all_snapshots("0xAAA")
        assert len(results) == 1
        assert results[0].market_id == "cond_2"
