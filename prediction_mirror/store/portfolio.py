from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from prediction_mirror.models.position import OurPosition


def _row_to_position(row: sqlite3.Row) -> OurPosition:
    return OurPosition(
        market_id=row["market_id"],
        asset_id=row["asset_id"],
        platform=row["platform"],
        outcome=row["outcome"],
        size=row["size"],
        avg_entry_price=row["avg_entry_price"],
        total_cost=row["total_cost"],
        realized_pnl=row["realized_pnl"],
        source_target=row["source_target"],
        dry_run=bool(row["dry_run"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def upsert_position(conn: sqlite3.Connection, pos: OurPosition) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO our_positions "
        "(market_id, asset_id, platform, outcome, size, avg_entry_price, total_cost, "
        "realized_pnl, source_target, dry_run, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            pos.market_id,
            pos.asset_id,
            pos.platform,
            pos.outcome,
            pos.size,
            pos.avg_entry_price,
            pos.total_cost,
            pos.realized_pnl,
            pos.source_target,
            int(pos.dry_run),
            pos.updated_at.isoformat(),
        ),
    )
    conn.commit()


def get_position(
    conn: sqlite3.Connection,
    market_id: str,
    asset_id: str,
    source_target: str,
) -> OurPosition | None:
    row = conn.execute(
        "SELECT * FROM our_positions "
        "WHERE market_id = ? AND asset_id = ? AND source_target = ?",
        (market_id, asset_id, source_target),
    ).fetchone()
    if row is None:
        return None
    return _row_to_position(row)


def get_all_positions(
    conn: sqlite3.Connection, dry_run: bool | None = None
) -> list[OurPosition]:
    if dry_run is not None:
        rows = conn.execute(
            "SELECT * FROM our_positions WHERE dry_run = ? ORDER BY market_id",
            (int(dry_run),),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM our_positions ORDER BY market_id"
        ).fetchall()
    return [_row_to_position(row) for row in rows]


def get_positions_by_target(
    conn: sqlite3.Connection, target_label: str
) -> list[OurPosition]:
    rows = conn.execute(
        "SELECT * FROM our_positions WHERE source_target = ? ORDER BY market_id",
        (target_label,),
    ).fetchall()
    return [_row_to_position(row) for row in rows]


def zero_out_position(
    conn: sqlite3.Connection,
    market_id: str,
    asset_id: str,
    source_target: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE our_positions SET size = 0, total_cost = 0, updated_at = ? "
        "WHERE market_id = ? AND asset_id = ? AND source_target = ?",
        (now, market_id, asset_id, source_target),
    )
    conn.commit()


def get_deployed_for_target(
    conn: sqlite3.Connection, target_label: str, dry_run: bool | None = None
) -> float:
    if dry_run is not None:
        row = conn.execute(
            "SELECT COALESCE(SUM(total_cost), 0) as deployed FROM our_positions "
            "WHERE source_target = ? AND dry_run = ? AND size > 0",
            (target_label, int(dry_run)),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COALESCE(SUM(total_cost), 0) as deployed FROM our_positions "
            "WHERE source_target = ? AND size > 0",
            (target_label,),
        ).fetchone()
    return row["deployed"]


def get_total_deployed(conn: sqlite3.Connection, dry_run: bool | None = None) -> float:
    if dry_run is not None:
        row = conn.execute(
            "SELECT COALESCE(SUM(total_cost), 0) as deployed FROM our_positions "
            "WHERE dry_run = ? AND size > 0",
            (int(dry_run),),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COALESCE(SUM(total_cost), 0) as deployed FROM our_positions "
            "WHERE size > 0"
        ).fetchone()
    return row["deployed"]


def get_allocation_summary(
    conn: sqlite3.Connection,
    targets: list,
    portfolio_value: float,
    dry_run: bool | None = None,
) -> dict[str, dict]:
    """Build allocation summary for dashboard display."""
    result = {}
    total_alloc = 0.0
    for t in targets:
        budget = portfolio_value * (t.allocation_pct / 100)
        deployed = get_deployed_for_target(conn, t.label, dry_run=dry_run)
        result[t.label] = {
            "allocation_pct": t.allocation_pct,
            "budget": budget,
            "deployed": deployed,
            "available": max(budget - deployed, 0),
        }
        total_alloc += t.allocation_pct
    reserve_pct = 100 - total_alloc
    if reserve_pct > 0:
        result["_reserve"] = {
            "available": portfolio_value * (reserve_pct / 100),
        }
    return result
