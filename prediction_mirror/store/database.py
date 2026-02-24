from __future__ import annotations

import sqlite3
from pathlib import Path

_connection: sqlite3.Connection | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS targets (
    label           TEXT PRIMARY KEY,
    platform        TEXT    NOT NULL,
    address         TEXT    NOT NULL,
    allocation_pct  REAL    NOT NULL,
    multiplier      REAL    NOT NULL DEFAULT 1.0,
    enabled         INTEGER NOT NULL DEFAULT 1,
    sizing_mode     TEXT    NOT NULL DEFAULT 'conviction',
    history_window  INTEGER NOT NULL DEFAULT 50,
    min_history     INTEGER NOT NULL DEFAULT 10,
    cold_start_pct  REAL    NOT NULL DEFAULT 50.0,
    conviction_floor_pct   REAL NOT NULL DEFAULT 10.0,
    conviction_ceiling_pct REAL NOT NULL DEFAULT 90.0,
    created_at      TEXT    NOT NULL,
    UNIQUE(platform, address)
);

CREATE TABLE IF NOT EXISTS target_trade_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    target_label    TEXT    NOT NULL,
    trade_usd       REAL    NOT NULL,
    detected_at     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trade_history_target ON target_trade_history(target_label);

CREATE TABLE IF NOT EXISTS target_snapshots (
    target_address  TEXT    NOT NULL,
    platform        TEXT    NOT NULL,
    market_id       TEXT    NOT NULL,
    asset_id        TEXT    NOT NULL,
    outcome         TEXT    NOT NULL,
    size            REAL    NOT NULL,
    avg_price       REAL,
    current_price   REAL,
    snapshot_time   TEXT    NOT NULL,
    PRIMARY KEY (target_address, platform, market_id, asset_id)
);

CREATE TABLE IF NOT EXISTS signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_type     TEXT    NOT NULL,
    target_address  TEXT    NOT NULL,
    target_label    TEXT    NOT NULL,
    platform        TEXT    NOT NULL,
    market_id       TEXT    NOT NULL,
    asset_id        TEXT    NOT NULL,
    outcome         TEXT    NOT NULL,
    target_delta    REAL    NOT NULL,
    target_prev_size REAL   NOT NULL DEFAULT 0,
    target_price    REAL,
    detected_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS executed_trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id       INTEGER REFERENCES signals(id),
    target_address  TEXT    NOT NULL,
    target_label    TEXT    NOT NULL,
    platform        TEXT    NOT NULL,
    side            TEXT    NOT NULL,
    market_id       TEXT    NOT NULL,
    asset_id        TEXT    NOT NULL,
    ordered_price   REAL    NOT NULL,
    ordered_size    REAL    NOT NULL,
    fill_price      REAL,
    fill_size       REAL,
    usd_amount      REAL,
    order_id        TEXT,
    success         INTEGER NOT NULL,
    dry_run         INTEGER NOT NULL,
    error           TEXT,
    executed_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS our_positions (
    market_id       TEXT    NOT NULL,
    asset_id        TEXT    NOT NULL,
    platform        TEXT    NOT NULL,
    outcome         TEXT    NOT NULL,
    size            REAL    NOT NULL DEFAULT 0,
    avg_entry_price REAL    NOT NULL DEFAULT 0,
    total_cost      REAL    NOT NULL DEFAULT 0,
    realized_pnl    REAL    NOT NULL DEFAULT 0,
    source_target   TEXT    NOT NULL,
    dry_run         INTEGER NOT NULL DEFAULT 0,
    updated_at      TEXT    NOT NULL,
    PRIMARY KEY (market_id, asset_id, source_target)
);

CREATE INDEX IF NOT EXISTS idx_signals_detected  ON signals(detected_at);
CREATE INDEX IF NOT EXISTS idx_signals_target     ON signals(target_label);
CREATE INDEX IF NOT EXISTS idx_trades_executed    ON executed_trades(executed_at);
CREATE INDEX IF NOT EXISTS idx_trades_target      ON executed_trades(target_label);
CREATE INDEX IF NOT EXISTS idx_positions_target   ON our_positions(source_target);
CREATE INDEX IF NOT EXISTS idx_positions_dry_run  ON our_positions(dry_run);
"""


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)


def init_db(path: str | Path = ":memory:") -> sqlite3.Connection:
    global _connection
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    _create_tables(conn)

    from prediction_mirror.store import settings as settings_mod

    settings_mod.seed_defaults(conn)
    conn.commit()
    _connection = conn
    return conn


def get_connection() -> sqlite3.Connection:
    if _connection is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _connection


def close() -> None:
    global _connection
    if _connection:
        _connection.close()
        _connection = None
