from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

DUST_THRESHOLD = 0.01


def upsert_goal(
    conn: sqlite3.Connection,
    target_label: str,
    market_id: str,
    asset_id: str,
    outcome: str,
    platform: str,
    delta: float,
    price: float,
) -> None:
    """Add or merge a failed trade into the pending goals.

    delta > 0 for a failed BUY, delta < 0 for a failed SELL.
    Merges with existing goal by adjusting net_delta and recalculating VWAP.
    Deletes goal if net_delta falls below dust threshold.
    """
    now = datetime.now(timezone.utc).isoformat()
    trade_usd = abs(delta) * price

    existing = conn.execute(
        "SELECT net_delta, total_usd FROM pending_goals "
        "WHERE target_label = ? AND market_id = ? AND asset_id = ?",
        (target_label, market_id, asset_id),
    ).fetchone()

    if existing is None:
        if abs(delta) < DUST_THRESHOLD:
            return
        conn.execute(
            "INSERT INTO pending_goals "
            "(target_label, market_id, asset_id, outcome, platform, "
            "net_delta, vwap, total_usd, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (target_label, market_id, asset_id, outcome, platform,
             delta, price, trade_usd, now, now),
        )
        conn.commit()
        return

    old_net = existing["net_delta"]
    old_usd = existing["total_usd"]

    new_net = old_net + delta

    # Adjust total_usd: same-direction adds, opposite-direction subtracts
    if (old_net >= 0 and delta >= 0) or (old_net <= 0 and delta <= 0):
        new_usd = old_usd + trade_usd
    else:
        new_usd = old_usd - trade_usd

    # If net crossed zero or is dust, clean up
    if abs(new_net) < DUST_THRESHOLD:
        conn.execute(
            "DELETE FROM pending_goals "
            "WHERE target_label = ? AND market_id = ? AND asset_id = ?",
            (target_label, market_id, asset_id),
        )
        conn.commit()
        return

    new_usd = max(new_usd, 0.0)
    new_vwap = new_usd / abs(new_net) if abs(new_net) > 0 else price

    conn.execute(
        "UPDATE pending_goals SET net_delta = ?, vwap = ?, total_usd = ?, "
        "updated_at = ? "
        "WHERE target_label = ? AND market_id = ? AND asset_id = ?",
        (new_net, new_vwap, new_usd, now,
         target_label, market_id, asset_id),
    )
    conn.commit()


def get_pending_goals(
    conn: sqlite3.Connection, target_label: str | None = None
) -> list[sqlite3.Row]:
    if target_label:
        return conn.execute(
            "SELECT * FROM pending_goals WHERE target_label = ? "
            "ORDER BY created_at",
            (target_label,),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM pending_goals ORDER BY created_at"
    ).fetchall()


def reduce_goal(
    conn: sqlite3.Connection,
    target_label: str,
    market_id: str,
    asset_id: str,
    filled_delta: float,
) -> None:
    """Reduce a goal's net_delta after a successful fill."""
    existing = conn.execute(
        "SELECT net_delta, vwap, total_usd FROM pending_goals "
        "WHERE target_label = ? AND market_id = ? AND asset_id = ?",
        (target_label, market_id, asset_id),
    ).fetchone()
    if existing is None:
        return

    old_net = existing["net_delta"]
    # Reduce toward zero
    if old_net > 0:
        new_net = old_net - filled_delta
    else:
        new_net = old_net + filled_delta

    if abs(new_net) < DUST_THRESHOLD:
        conn.execute(
            "DELETE FROM pending_goals "
            "WHERE target_label = ? AND market_id = ? AND asset_id = ?",
            (target_label, market_id, asset_id),
        )
        conn.commit()
        return

    # Adjust total_usd proportionally
    ratio = abs(new_net) / abs(old_net) if abs(old_net) > 0 else 0
    new_usd = existing["total_usd"] * ratio
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        "UPDATE pending_goals SET net_delta = ?, total_usd = ?, "
        "updated_at = ? "
        "WHERE target_label = ? AND market_id = ? AND asset_id = ?",
        (new_net, new_usd, now, target_label, market_id, asset_id),
    )
    conn.commit()


def delete_goal(
    conn: sqlite3.Connection,
    target_label: str,
    market_id: str,
    asset_id: str,
) -> None:
    conn.execute(
        "DELETE FROM pending_goals "
        "WHERE target_label = ? AND market_id = ? AND asset_id = ?",
        (target_label, market_id, asset_id),
    )
    conn.commit()
