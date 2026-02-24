from __future__ import annotations

from datetime import datetime, timezone

from prediction_mirror.dashboard.listener import DashboardListener
from prediction_mirror.dashboard.portfolio_view import (
    render_allocation_table,
    render_positions_table,
)
from prediction_mirror.dashboard.renderer import render_dashboard, render_header
from prediction_mirror.models.position import OurPosition
from prediction_mirror.store import Store, init_db

NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


class TestRenderHeader:
    def test_dry_run_header(self):
        header = render_header("2h 14m", dry_run=True, target_count=3)
        text = header.plain
        assert "PREDICTION MIRROR TRADER" in text
        assert "DRY RUN" in text
        assert "3 targets" in text

    def test_live_header(self):
        header = render_header("1h 0m", dry_run=False, target_count=1)
        text = header.plain
        assert "LIVE" in text


class TestAllocationTable:
    def test_render_allocation(self):
        summary = {
            "Whale": {"allocation_pct": 50.0, "budget": 500.0, "deployed": 200.0, "available": 300.0},
            "Degen": {"allocation_pct": 30.0, "budget": 300.0, "deployed": 0.0, "available": 300.0},
            "_reserve": {"available": 200.0},
        }
        table = render_allocation_table(summary)
        assert table.title == "ALLOCATION"
        assert table.row_count == 3


class TestPositionsTable:
    def test_render_positions(self):
        positions = [
            OurPosition(
                market_id="cond_abc123", asset_id="tok_1", platform="polymarket",
                outcome="Yes", size=15.0, avg_entry_price=0.52, total_cost=7.80,
                realized_pnl=0.0, source_target="Whale", dry_run=True, updated_at=NOW,
            ),
        ]
        table = render_positions_table(positions)
        assert table.title == "POSITIONS (1)"
        assert table.row_count == 1

    def test_empty_positions(self):
        table = render_positions_table([])
        assert table.title == "POSITIONS (0)"
        assert table.row_count == 0


class TestDashboardListener:
    def test_initial_state(self):
        conn = init_db(":memory:")
        store = Store(conn)
        listener = DashboardListener(store)
        assert listener.status == "starting"
        assert listener.errors == []
        conn.close()

    def test_error_collection(self):
        conn = init_db(":memory:")
        store = Store(conn)
        listener = DashboardListener(store)
        listener.on_error("Test error", {"target": "Whale"})
        assert len(listener.errors) == 1
        assert listener.errors[0][0] == "Test error"
        conn.close()

    def test_status_change(self):
        conn = init_db(":memory:")
        store = Store(conn)
        listener = DashboardListener(store)
        listener.on_status_change("running", "Engine started")
        assert listener.status == "running"
        conn.close()

    def test_uptime_format(self):
        conn = init_db(":memory:")
        store = Store(conn)
        listener = DashboardListener(store)
        # Just verify it returns a string without errors
        uptime = listener.uptime
        assert isinstance(uptime, str)
        assert "m" in uptime
        conn.close()


class TestRenderDashboard:
    def test_full_render(self):
        panel = render_dashboard(
            uptime="2h 14m",
            dry_run=True,
            target_count=2,
            allocation_summary={
                "Whale": {"allocation_pct": 50.0, "budget": 500.0, "deployed": 0.0, "available": 500.0},
            },
            positions=[],
            signals=[],
            trades=[],
            errors=[],
        )
        # Just verify it produces a renderable without error
        assert panel is not None
