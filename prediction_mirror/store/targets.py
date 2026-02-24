from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from prediction_mirror.models.target import TargetConfig


def _row_to_target(row: sqlite3.Row) -> TargetConfig:
    return TargetConfig(
        label=row["label"],
        platform=row["platform"],
        address=row["address"],
        allocation_pct=row["allocation_pct"],
        multiplier=row["multiplier"],
        enabled=bool(row["enabled"]),
    )


def _get_total_allocation(conn: sqlite3.Connection, exclude_label: str | None = None) -> float:
    if exclude_label:
        row = conn.execute(
            "SELECT COALESCE(SUM(allocation_pct), 0) as total FROM targets "
            "WHERE enabled = 1 AND label != ?",
            (exclude_label,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COALESCE(SUM(allocation_pct), 0) as total FROM targets WHERE enabled = 1"
        ).fetchone()
    return row["total"]


def add_target(conn: sqlite3.Connection, target: TargetConfig) -> None:
    current_total = _get_total_allocation(conn)
    if target.enabled and current_total + target.allocation_pct > 100.0:
        raise ValueError(
            f"Total allocation would exceed 100% "
            f"({current_total + target.allocation_pct:.1f}%)"
        )
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO targets (label, platform, address, allocation_pct, multiplier, enabled, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            target.label,
            target.platform,
            target.address,
            target.allocation_pct,
            target.multiplier,
            int(target.enabled),
            now,
        ),
    )
    conn.commit()


def get_enabled(conn: sqlite3.Connection) -> list[TargetConfig]:
    rows = conn.execute(
        "SELECT * FROM targets WHERE enabled = 1 ORDER BY label"
    ).fetchall()
    return [_row_to_target(row) for row in rows]


def get_all(conn: sqlite3.Connection) -> list[TargetConfig]:
    rows = conn.execute("SELECT * FROM targets ORDER BY label").fetchall()
    return [_row_to_target(row) for row in rows]


def get_by_label(conn: sqlite3.Connection, label: str) -> TargetConfig | None:
    row = conn.execute("SELECT * FROM targets WHERE label = ?", (label,)).fetchone()
    if row is None:
        return None
    return _row_to_target(row)


def enable_target(conn: sqlite3.Connection, label: str) -> None:
    target = get_by_label(conn, label)
    if target is None:
        raise KeyError(f"Target not found: {label}")
    if target.enabled:
        return
    current_total = _get_total_allocation(conn)
    if current_total + target.allocation_pct > 100.0:
        raise ValueError(
            f"Total allocation would exceed 100% "
            f"({current_total + target.allocation_pct:.1f}%)"
        )
    conn.execute("UPDATE targets SET enabled = 1 WHERE label = ?", (label,))
    conn.commit()


def disable_target(conn: sqlite3.Connection, label: str) -> None:
    target = get_by_label(conn, label)
    if target is None:
        raise KeyError(f"Target not found: {label}")
    conn.execute("UPDATE targets SET enabled = 0 WHERE label = ?", (label,))
    conn.commit()


def remove_target(conn: sqlite3.Connection, label: str) -> None:
    target = get_by_label(conn, label)
    if target is None:
        raise KeyError(f"Target not found: {label}")
    conn.execute("DELETE FROM targets WHERE label = ?", (label,))
    conn.commit()


def set_allocation(conn: sqlite3.Connection, label: str, pct: float) -> None:
    target = get_by_label(conn, label)
    if target is None:
        raise KeyError(f"Target not found: {label}")
    if pct < 0 or pct > 100:
        raise ValueError(f"Allocation must be 0-100, got {pct}")
    if target.enabled:
        current_total = _get_total_allocation(conn, exclude_label=label)
        if current_total + pct > 100.0:
            raise ValueError(
                f"Total allocation would exceed 100% ({current_total + pct:.1f}%)"
            )
    conn.execute(
        "UPDATE targets SET allocation_pct = ? WHERE label = ?", (pct, label)
    )
    conn.commit()


def validate_allocations(conn: sqlite3.Connection) -> bool:
    total = _get_total_allocation(conn)
    return total <= 100.0
