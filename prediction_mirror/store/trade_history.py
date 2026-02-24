from __future__ import annotations

import sqlite3
from datetime import datetime


def record_trade(
    conn: sqlite3.Connection,
    target_label: str,
    trade_usd: float,
    detected_at: datetime,
) -> None:
    conn.execute(
        "INSERT INTO target_trade_history (target_label, trade_usd, detected_at) "
        "VALUES (?, ?, ?)",
        (target_label, trade_usd, detected_at.isoformat()),
    )
    conn.commit()


def get_recent_trades(
    conn: sqlite3.Connection,
    target_label: str,
    limit: int = 50,
) -> list[float]:
    """Return the most recent trade USD values for percentile calculation."""
    rows = conn.execute(
        "SELECT trade_usd FROM target_trade_history "
        "WHERE target_label = ? ORDER BY detected_at DESC LIMIT ?",
        (target_label, limit),
    ).fetchall()
    return [row["trade_usd"] for row in rows]
