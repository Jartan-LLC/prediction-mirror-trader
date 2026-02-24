from __future__ import annotations

import pytest

from prediction_mirror.models.settings import Settings
from prediction_mirror.store import Store, init_db
from prediction_mirror.store import settings as settings_mod


@pytest.fixture
def store():
    conn = init_db(":memory:")
    yield Store(conn)
    conn.close()


class TestSeedDefaults:
    def test_defaults_seeded(self, store: Store):
        all_settings = store.get_all_settings()
        assert len(all_settings) == len(settings_mod.DEFAULTS)

    def test_default_values_match(self, store: Store):
        for key, expected in settings_mod.DEFAULTS.items():
            assert store.get_setting(key) == expected

    def test_seed_idempotent(self, store: Store):
        # Seed again — existing values should not change
        store.set_setting("dry_run", "false")
        settings_mod.seed_defaults(store.conn)
        assert store.get_setting("dry_run") == "false"


class TestGetCurrent:
    def test_returns_settings_dataclass(self, store: Store):
        s = store.get_settings()
        assert isinstance(s, Settings)

    def test_default_values(self, store: Store):
        s = store.get_settings()
        assert s.poll_interval_seconds == 2
        assert s.dry_run is True
        assert s.log_level == "INFO"

    def test_reflects_changes(self, store: Store):
        store.set_setting("dry_run", "false")
        s = store.get_settings()
        assert s.dry_run is False

    def test_int_coercion(self, store: Store):
        store.set_setting("poll_interval_seconds", "10")
        s = store.get_settings()
        assert s.poll_interval_seconds == 10
        assert isinstance(s.poll_interval_seconds, int)

    def test_float_coercion(self, store: Store):
        store.set_setting("slippage_tolerance_pct", "5.5")
        s = store.get_settings()
        assert s.slippage_tolerance_pct == 5.5


class TestSetValue:
    def test_set_and_get(self, store: Store):
        store.set_setting("max_order_usd", "250.0")
        assert store.get_setting("max_order_usd") == "250.0"

    def test_unknown_key_raises(self, store: Store):
        with pytest.raises(KeyError, match="Unknown setting"):
            store.set_setting("nonexistent", "value")

    def test_invalid_bool_raises(self, store: Store):
        with pytest.raises(ValueError, match="Cannot parse"):
            store.set_setting("dry_run", "maybe")

    def test_invalid_int_raises(self, store: Store):
        with pytest.raises(ValueError):
            store.set_setting("poll_interval_seconds", "not_a_number")


class TestGetValue:
    def test_existing_key(self, store: Store):
        val = store.get_setting("dry_run")
        assert val == "true"

    def test_unknown_key_raises(self, store: Store):
        with pytest.raises(KeyError, match="Unknown setting"):
            store.get_setting("bogus")


class TestGetAll:
    def test_returns_all_pairs(self, store: Store):
        all_settings = store.get_all_settings()
        assert len(all_settings) == len(settings_mod.DEFAULTS)
        keys = [k for k, _ in all_settings]
        assert "dry_run" in keys
        assert "poll_interval_seconds" in keys

    def test_sorted_by_key(self, store: Store):
        all_settings = store.get_all_settings()
        keys = [k for k, _ in all_settings]
        assert keys == sorted(keys)
