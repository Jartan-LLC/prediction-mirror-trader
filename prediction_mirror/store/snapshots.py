from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from prediction_mirror.models.position import TargetPosition


def _row_to_target_position(row: sqlite3.Row) -> TargetPosition:
    return TargetPosition(
        target_address=row["target_address"],
        platform=row["platform"],
        market_id=row["market_id"],
        asset_id=row["asset_id"],
        outcome=row["outcome"],
        size=row["size"],
        avg_price=row["avg_price"] or 0.0,
        current_price=row["current_price"] or 0.0,
        snapshot_time=datetime.fromisoformat(row["snapshot_time"]),
    )


def upsert_snapshot(conn: sqlite3.Connection, pos: TargetPosition) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO target_snapshots "
        "(target_address, platform, market_id, asset_id, outcome, size, avg_price, current_price, snapshot_time) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            pos.target_address,
            pos.platform,
            pos.market_id,
            pos.asset_id,
            pos.outcome,
            pos.size,
            pos.avg_price,
            pos.current_price,
            pos.snapshot_time.isoformat(),
        ),
    )
    conn.commit()


def get_snapshot(
    conn: sqlite3.Connection,
    target_address: str,
    platform: str,
    market_id: str,
    asset_id: str,
) -> TargetPosition | None:
    row = conn.execute(
        "SELECT * FROM target_snapshots "
        "WHERE target_address = ? AND platform = ? AND market_id = ? AND asset_id = ?",
        (target_address, platform, market_id, asset_id),
    ).fetchone()
    if row is None:
        return None
    return _row_to_target_position(row)


def get_all_snapshots(
    conn: sqlite3.Connection, target_address: str
) -> list[TargetPosition]:
    rows = conn.execute(
        "SELECT * FROM target_snapshots WHERE target_address = ? ORDER BY market_id",
        (target_address,),
    ).fetchall()
    return [_row_to_target_position(row) for row in rows]


def delete_snapshot(
    conn: sqlite3.Connection,
    target_address: str,
    platform: str,
    market_id: str,
    asset_id: str,
) -> None:
    conn.execute(
        "DELETE FROM target_snapshots "
        "WHERE target_address = ? AND platform = ? AND market_id = ? AND asset_id = ?",
        (target_address, platform, market_id, asset_id),
    )
    conn.commit()


def delete_stale_snapshots(conn: sqlite3.Connection, older_than: datetime) -> int:
    cursor = conn.execute(
        "DELETE FROM target_snapshots WHERE snapshot_time < ?",
        (older_than.isoformat(),),
    )
    conn.commit()
    return cursor.rowcount
