from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from prediction_mirror.models.order import OrderResult


def insert_trade(conn: sqlite3.Connection, result: OrderResult, signal_id: int) -> int:
    order = result.order
    cursor = conn.execute(
        "INSERT INTO executed_trades "
        "(signal_id, target_address, target_label, platform, side, market_id, asset_id, "
        "ordered_price, ordered_size, fill_price, fill_size, usd_amount, order_id, "
        "success, dry_run, error, executed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            signal_id,
            order.signal.target.address,
            order.signal.target.label,
            order.signal.platform,
            order.side.value,
            order.asset_id,
            order.asset_id,
            order.price,
            order.size,
            result.fill_price,
            result.fill_size,
            order.usd_amount,
            result.order_id,
            int(result.success),
            int(order.dry_run),
            result.error,
            result.executed_at.isoformat(),
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_recent_trades(conn: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM executed_trades ORDER BY executed_at DESC LIMIT ?",
        (limit,),
    ).fetchall()


def get_trades_for_target(
    conn: sqlite3.Connection,
    target_label: str,
    since: datetime | None = None,
) -> list[sqlite3.Row]:
    if since:
        return conn.execute(
            "SELECT * FROM executed_trades "
            "WHERE target_label = ? AND executed_at >= ? ORDER BY executed_at DESC",
            (target_label, since.isoformat()),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM executed_trades WHERE target_label = ? ORDER BY executed_at DESC",
        (target_label,),
    ).fetchall()


def get_trade_summary(
    conn: sqlite3.Connection, dry_run: bool | None = None
) -> dict:
    where = ""
    params: list = []
    if dry_run is not None:
        where = "WHERE dry_run = ?"
        params = [int(dry_run)]

    row = conn.execute(
        f"SELECT "
        f"  COUNT(*) as total_trades, "
        f"  SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful, "
        f"  SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failed, "
        f"  SUM(CASE WHEN success = 1 THEN usd_amount ELSE 0 END) as total_volume "
        f"FROM executed_trades {where}",
        params,
    ).fetchone()

    return {
        "total_trades": row["total_trades"],
        "successful": row["successful"] or 0,
        "failed": row["failed"] or 0,
        "total_volume": row["total_volume"] or 0.0,
    }
