from __future__ import annotations

import sqlite3

from prediction_mirror.models.settings import Settings

DEFAULTS: dict[str, str] = {
    "poll_interval_seconds": "2",
    "slippage_tolerance_pct": "2.0",
    "min_order_usd": "1.0",
    "max_order_usd": "500.0",
    "max_position_usd": "1000.0",
    "redeemer_interval_seconds": "7200",
    "dashboard_refresh_seconds": "30",
    "dry_run": "true",
    "dry_run_balance_usd": "1000.0",
    "dry_run_cash": "-1",
    "log_level": "INFO",
}

_BOOL_TRUE = {"true", "1", "yes"}
_BOOL_FALSE = {"false", "0", "no"}

_FIELD_TYPES: dict[str, type] = {
    "poll_interval_seconds": int,
    "slippage_tolerance_pct": float,
    "min_order_usd": float,
    "max_order_usd": float,
    "max_position_usd": float,
    "redeemer_interval_seconds": int,
    "dashboard_refresh_seconds": int,
    "dry_run": bool,
    "dry_run_balance_usd": float,
    "dry_run_cash": float,
    "log_level": str,
}


def _coerce(key: str, value: str) -> int | float | bool | str:
    field_type = _FIELD_TYPES.get(key, str)
    if field_type is bool:
        lower = value.lower()
        if lower in _BOOL_TRUE:
            return True
        if lower in _BOOL_FALSE:
            return False
        raise ValueError(f"Cannot parse '{value}' as bool for setting '{key}'")
    return field_type(value)


def seed_defaults(conn: sqlite3.Connection) -> None:
    for key, value in DEFAULTS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )


def get_current(conn: sqlite3.Connection) -> Settings:
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    kwargs = {}
    for row in rows:
        key, value = row["key"], row["value"]
        if key in _FIELD_TYPES:
            kwargs[key] = _coerce(key, value)
    return Settings(**kwargs)


def get_value(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        raise KeyError(f"Unknown setting: {key}")
    return row["value"]


def set_value(conn: sqlite3.Connection, key: str, value: str) -> None:
    if key not in DEFAULTS:
        raise KeyError(f"Unknown setting: {key}")
    # Validate coercion before saving
    _coerce(key, value)
    conn.execute("UPDATE settings SET value = ? WHERE key = ?", (value, key))
    conn.commit()


def get_all(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    rows = conn.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
    return [(row["key"], row["value"]) for row in rows]
