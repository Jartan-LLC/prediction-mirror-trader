from __future__ import annotations

from datetime import datetime, timezone

import httpx

from prediction_mirror.models.position import TargetPosition
import logging

from prediction_mirror.platforms.errors import FatalError, TransientError
from prediction_mirror.platforms.polymarket.config import DATA_API_URL
logger = logging.getLogger(__name__)


def _classify_http_error(status_code: int, detail: str = "") -> None:
    if status_code == 429 or status_code >= 500:
        raise TransientError(f"Data API {status_code}: {detail}")
    if status_code >= 400:
        raise FatalError(f"Data API {status_code}: {detail}")


def _parse_position(item: dict, target_address: str) -> TargetPosition:
    return TargetPosition(
        target_address=target_address,
        platform="polymarket",
        market_id=item.get("conditionId", item.get("condition_id", "")),
        asset_id=item.get("asset", ""),
        outcome=item.get("outcome", ""),
        size=float(item.get("size", 0)),
        avg_price=float(item.get("avgPrice", item.get("avg_price", 0))),
        current_price=float(item.get("curPrice", item.get("cur_price", 0))),
        snapshot_time=datetime.now(timezone.utc),
    )


async def fetch_positions(
    client: httpx.AsyncClient, address: str
) -> list[TargetPosition]:
    """Fetch target's positions from the Data API."""
    try:
        resp = await client.get(
            f"{DATA_API_URL}/positions",
            params={"user": address},
            timeout=10.0,
        )
    except httpx.TimeoutException as e:
        raise TransientError(f"Data API timeout: {e}") from e
    except httpx.ConnectError as e:
        raise TransientError(f"Data API connection error: {e}") from e

    if resp.status_code != 200:
        _classify_http_error(resp.status_code, resp.text[:200])

    data = resp.json()
    positions = []
    for item in data if isinstance(data, list) else []:
        size = float(item.get("size", 0))
        if size > 0:
            positions.append(_parse_position(item, address))
    return positions


async def fetch_portfolio_value(
    client: httpx.AsyncClient, address: str
) -> float:
    """Sum of (size * current_price) for all positions."""
    positions = await fetch_positions(client, address)
    return sum(p.size * p.current_price for p in positions)


async def fetch_trade_history(
    client: httpx.AsyncClient, address: str, limit: int = 50
) -> list[float]:
    """Fetch recent trade USD values from the Data API activity endpoint."""
    try:
        resp = await client.get(
            f"{DATA_API_URL}/activity",
            params={"user": address, "type": "TRADE", "limit": limit},
            timeout=10.0,
        )
    except httpx.TimeoutException as e:
        raise TransientError(f"Data API timeout: {e}") from e
    except httpx.ConnectError as e:
        raise TransientError(f"Data API connection error: {e}") from e

    if resp.status_code != 200:
        _classify_http_error(resp.status_code, resp.text[:200])

    data = resp.json()
    values = []
    for item in data if isinstance(data, list) else []:
        usd = float(item.get("usdcSize", 0))
        if usd > 0:
            values.append(usd)
    return values
