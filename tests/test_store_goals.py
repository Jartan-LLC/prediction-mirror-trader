from __future__ import annotations

import pytest

from prediction_mirror.store import Store, init_db


class TestGoals:
    def _store(self):
        conn = init_db(":memory:")
        return Store(conn), conn

    def test_create_buy_goal(self):
        store, conn = self._store()
        store.upsert_goal("Whale", "m1", "a1", "Yes", "poly", 100.0, 0.50)
        goals = store.get_pending_goals()
        assert len(goals) == 1
        assert goals[0]["net_delta"] == 100.0
        assert goals[0]["vwap"] == 0.50
        conn.close()

    def test_create_sell_goal(self):
        store, conn = self._store()
        store.upsert_goal("Whale", "m1", "a1", "Yes", "poly", -50.0, 0.60)
        goals = store.get_pending_goals()
        assert len(goals) == 1
        assert goals[0]["net_delta"] == -50.0
        conn.close()

    def test_merge_same_direction(self):
        store, conn = self._store()
        store.upsert_goal("Whale", "m1", "a1", "Yes", "poly", 200.0, 0.40)
        store.upsert_goal("Whale", "m1", "a1", "Yes", "poly", 300.0, 0.45)
        goals = store.get_pending_goals()
        assert len(goals) == 1
        assert goals[0]["net_delta"] == 500.0
        # VWAP = (200*0.40 + 300*0.45) / 500 = (80+135)/500 = 0.43
        assert goals[0]["vwap"] == pytest.approx(0.43)
        conn.close()

    def test_merge_conflicting_reduces(self):
        store, conn = self._store()
        store.upsert_goal("Whale", "m1", "a1", "Yes", "poly", 300.0, 0.40)
        store.upsert_goal("Whale", "m1", "a1", "Yes", "poly", -100.0, 0.50)
        goals = store.get_pending_goals()
        assert len(goals) == 1
        assert goals[0]["net_delta"] == 200.0
        conn.close()

    def test_merge_conflicting_cancels(self):
        store, conn = self._store()
        store.upsert_goal("Whale", "m1", "a1", "Yes", "poly", 100.0, 0.40)
        store.upsert_goal("Whale", "m1", "a1", "Yes", "poly", -100.0, 0.50)
        goals = store.get_pending_goals()
        assert len(goals) == 0
        conn.close()

    def test_merge_conflicting_flips(self):
        store, conn = self._store()
        store.upsert_goal("Whale", "m1", "a1", "Yes", "poly", 100.0, 0.40)
        store.upsert_goal("Whale", "m1", "a1", "Yes", "poly", -200.0, 0.50)
        goals = store.get_pending_goals()
        assert len(goals) == 1
        assert goals[0]["net_delta"] == -100.0
        conn.close()

    def test_reduce_goal(self):
        store, conn = self._store()
        store.upsert_goal("Whale", "m1", "a1", "Yes", "poly", 500.0, 0.40)
        store.reduce_goal("Whale", "m1", "a1", 200.0)
        goals = store.get_pending_goals()
        assert len(goals) == 1
        assert goals[0]["net_delta"] == 300.0
        conn.close()

    def test_reduce_goal_to_zero_deletes(self):
        store, conn = self._store()
        store.upsert_goal("Whale", "m1", "a1", "Yes", "poly", 100.0, 0.40)
        store.reduce_goal("Whale", "m1", "a1", 100.0)
        goals = store.get_pending_goals()
        assert len(goals) == 0
        conn.close()

    def test_delete_goal(self):
        store, conn = self._store()
        store.upsert_goal("Whale", "m1", "a1", "Yes", "poly", 100.0, 0.40)
        store.delete_goal("Whale", "m1", "a1")
        assert len(store.get_pending_goals()) == 0
        conn.close()

    def test_filter_by_target(self):
        store, conn = self._store()
        store.upsert_goal("Whale", "m1", "a1", "Yes", "poly", 100.0, 0.40)
        store.upsert_goal("Degen", "m2", "a2", "No", "poly", 50.0, 0.30)
        assert len(store.get_pending_goals("Whale")) == 1
        assert len(store.get_pending_goals("Degen")) == 1
        assert len(store.get_pending_goals()) == 2
        conn.close()

    def test_dust_threshold(self):
        store, conn = self._store()
        store.upsert_goal("Whale", "m1", "a1", "Yes", "poly", 0.001, 0.40)
        assert len(store.get_pending_goals()) == 0
        conn.close()
