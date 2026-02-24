from __future__ import annotations

import pytest

from prediction_mirror.models.target import TargetConfig
from prediction_mirror.store import Store, init_db


@pytest.fixture
def store():
    conn = init_db(":memory:")
    yield Store(conn)
    conn.close()


def _make_target(label="Whale", platform="polymarket", address="0xAAA", pct=50.0, **kw):
    return TargetConfig(label=label, platform=platform, address=address, allocation_pct=pct, **kw)


class TestAddTarget:
    def test_add_and_retrieve(self, store: Store):
        t = _make_target()
        store.add_target(t)
        result = store.get_target("Whale")
        assert result is not None
        assert result.label == "Whale"
        assert result.allocation_pct == 50.0

    def test_allocation_over_100_raises(self, store: Store):
        store.add_target(_make_target("A", address="0xA", pct=60.0))
        with pytest.raises(ValueError, match="exceed 100%"):
            store.add_target(_make_target("B", address="0xB", pct=50.0))

    def test_disabled_target_skips_allocation_check(self, store: Store):
        store.add_target(_make_target("A", address="0xA", pct=60.0))
        # Disabled target with 50% — should not trigger allocation check
        store.add_target(_make_target("B", address="0xB", pct=50.0, enabled=False))
        result = store.get_target("B")
        assert result is not None
        assert not result.enabled

    def test_duplicate_label_raises(self, store: Store):
        store.add_target(_make_target())
        with pytest.raises(Exception):  # IntegrityError
            store.add_target(_make_target(address="0xBBB"))

    def test_duplicate_platform_address_raises(self, store: Store):
        store.add_target(_make_target("A"))
        with pytest.raises(Exception):  # UNIQUE constraint
            store.add_target(_make_target("B"))  # same platform+address


class TestGetTargets:
    def test_get_enabled(self, store: Store):
        store.add_target(_make_target("A", address="0xA", pct=30.0))
        store.add_target(_make_target("B", address="0xB", pct=20.0, enabled=False))
        enabled = store.get_enabled_targets()
        assert len(enabled) == 1
        assert enabled[0].label == "A"

    def test_get_all(self, store: Store):
        store.add_target(_make_target("A", address="0xA", pct=30.0))
        store.add_target(_make_target("B", address="0xB", pct=20.0, enabled=False))
        all_targets = store.get_all_targets()
        assert len(all_targets) == 2

    def test_get_by_label_found(self, store: Store):
        store.add_target(_make_target("Whale"))
        assert store.get_target("Whale") is not None

    def test_get_by_label_not_found(self, store: Store):
        assert store.get_target("Missing") is None


class TestEnableDisable:
    def test_disable_target(self, store: Store):
        store.add_target(_make_target("A", address="0xA", pct=30.0))
        store.disable_target("A")
        assert store.get_target("A").enabled is False

    def test_enable_target(self, store: Store):
        store.add_target(_make_target("A", address="0xA", pct=30.0, enabled=False))
        store.enable_target("A")
        assert store.get_target("A").enabled is True

    def test_enable_missing_raises(self, store: Store):
        with pytest.raises(KeyError, match="Target not found"):
            store.enable_target("Ghost")

    def test_disable_missing_raises(self, store: Store):
        with pytest.raises(KeyError, match="Target not found"):
            store.disable_target("Ghost")

    def test_enable_would_exceed_allocation(self, store: Store):
        store.add_target(_make_target("A", address="0xA", pct=60.0))
        store.add_target(_make_target("B", address="0xB", pct=50.0, enabled=False))
        with pytest.raises(ValueError, match="exceed 100%"):
            store.enable_target("B")


class TestRemoveTarget:
    def test_remove(self, store: Store):
        store.add_target(_make_target())
        store.remove_target("Whale")
        assert store.get_target("Whale") is None

    def test_remove_missing_raises(self, store: Store):
        with pytest.raises(KeyError, match="Target not found"):
            store.remove_target("Ghost")


class TestSetAllocation:
    def test_set_allocation(self, store: Store):
        store.add_target(_make_target("A", address="0xA", pct=30.0))
        store.set_allocation("A", 50.0)
        assert store.get_target("A").allocation_pct == 50.0

    def test_set_allocation_missing_raises(self, store: Store):
        with pytest.raises(KeyError, match="Target not found"):
            store.set_allocation("Ghost", 10.0)

    def test_set_allocation_invalid_range(self, store: Store):
        store.add_target(_make_target())
        with pytest.raises(ValueError, match="Allocation must be 0-100"):
            store.set_allocation("Whale", -5.0)

    def test_set_allocation_exceeds_100(self, store: Store):
        store.add_target(_make_target("A", address="0xA", pct=60.0))
        store.add_target(_make_target("B", address="0xB", pct=30.0))
        with pytest.raises(ValueError, match="exceed 100%"):
            store.set_allocation("B", 50.0)

    def test_validate_allocations(self, store: Store):
        store.add_target(_make_target("A", address="0xA", pct=50.0))
        store.add_target(_make_target("B", address="0xB", pct=40.0))
        from prediction_mirror.store.targets import validate_allocations
        assert validate_allocations(store.conn) is True
