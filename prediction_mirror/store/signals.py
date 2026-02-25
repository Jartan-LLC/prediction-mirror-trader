from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from prediction_mirror.models.signal import Signal


def insert_signal(conn: sqlite3.Connection, signal: Signal) -> int:
    cursor = conn.execute(
        "INSERT INTO signals "
        "(signal_type, target_address, target_label, platform, market_id, asset_id, "
        "outcome, target_delta, target_prev_size, target_price, detected_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            signal.signal_type.value,
            signal.target.address,
            signal.target.label,
            signal.platform,
            signal.market_id,
            signal.asset_id,
            signal.outcome,
            signal.target_delta,
            signal.target_prev_size,
            signal.target_price,
            signal.detected_at.isoformat(),
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_recent_signals(
    conn: sqlite3.Connection, target_label: str, minutes: int = 60
) -> list[sqlite3.Row]:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    return conn.execute(
        "SELECT * FROM signals WHERE target_label = ? AND detected_at >= ? "
        "ORDER BY detected_at DESC",
        (target_label, cutoff),
    ).fetchall()


def get_signal_history(
    conn: sqlite3.Connection,
    since: datetime | None = None,
    limit: int = 100,
) -> list[sqlite3.Row]:
    if since:
        return conn.execute(
            "SELECT * FROM signals WHERE detected_at >= ? ORDER BY detected_at DESC LIMIT ?",
            (since.isoformat(), limit),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM signals ORDER BY detected_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
