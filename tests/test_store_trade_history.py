from __future__ import annotations

from datetime import datetime, timezone

from prediction_mirror.store import Store, init_db

NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


class TestTradeHistory:
    def _store(self):
        conn = init_db(":memory:")
        return Store(conn), conn

    def test_record_and_retrieve(self):
        store, conn = self._store()
        store.record_observed_trade("Whale", 55.0, NOW)
        store.record_observed_trade("Whale", 110.0, NOW)
        history = store.get_trade_history("Whale")
        assert len(history) == 2
        conn.close()

    def test_returns_usd_values(self):
        store, conn = self._store()
        store.record_observed_trade("Whale", 55.0, NOW)
        store.record_observed_trade("Whale", 110.0, NOW)
        history = store.get_trade_history("Whale")
        assert set(history) == {55.0, 110.0}
        conn.close()

    def test_respects_limit(self):
        store, conn = self._store()
        for i in range(20):
            store.record_observed_trade("Whale", float(i), NOW)
        history = store.get_trade_history("Whale", limit=10)
        assert len(history) == 10
        conn.close()

    def test_filters_by_target(self):
        store, conn = self._store()
        store.record_observed_trade("Whale", 100.0, NOW)
        store.record_observed_trade("Degen", 200.0, NOW)
        assert len(store.get_trade_history("Whale")) == 1
        assert len(store.get_trade_history("Degen")) == 1
        conn.close()

    def test_empty_history(self):
        store, conn = self._store()
        assert store.get_trade_history("Nobody") == []
        conn.close()
