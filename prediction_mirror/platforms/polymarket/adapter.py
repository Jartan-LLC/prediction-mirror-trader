from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

from prediction_mirror.models.market import Market, MarketStatus
from prediction_mirror.models.order import OrderResult, SizedOrder
from prediction_mirror.models.position import OurPosition, TargetPosition
from prediction_mirror.models.wallet import WalletState
from prediction_mirror.platforms.base import PlatformAdapter
from prediction_mirror.platforms.errors import FatalError, TransientError
from prediction_mirror.platforms.polymarket import blockchain, data_api
from prediction_mirror.platforms.polymarket.config import (
    USDC_DECIMALS,
    load_private_key,
    load_rpc_url,
)
import logging

logger = logging.getLogger(__name__)


class PolymarketAdapter(PlatformAdapter):
    """Polymarket adapter wrapping pmxt for trading, httpx for data, web3 for chain."""

    def __init__(
        self,
        private_key: str,
        rpc_url: str,
        pmxt_client: object | None = None,
        w3: object | None = None,
        http_client: httpx.AsyncClient | None = None,
    ):
        self._private_key = private_key
        self._rpc_url = rpc_url
        self._pmxt = pmxt_client
        self._w3 = w3
        self._http = http_client
        self._address: str | None = None

    @classmethod
    def from_env(cls) -> PolymarketAdapter:
        return cls(
            private_key=load_private_key(),
            rpc_url=load_rpc_url(),
        )

    async def initialize(self) -> None:
        if self._http is None:
            self._http = httpx.AsyncClient()

        if self._pmxt is None:
            try:
                import pmxt

                self._pmxt = await asyncio.to_thread(
                    pmxt.Polymarket, private_key=self._private_key
                )
            except Exception as e:
                raise FatalError(f"Failed to initialize pmxt: {e}") from e

        if self._w3 is None:
            try:
                from web3 import Web3

                self._w3 = Web3(Web3.HTTPProvider(self._rpc_url))
            except Exception as e:
                raise FatalError(f"Failed to initialize web3: {e}") from e

        # Derive address from private key
        try:
            account = self._w3.eth.account.from_key(self._private_key)
            self._address = account.address
        except Exception as e:
            raise FatalError(f"Invalid private key: {e}") from e

        logger.info(f"Initialized Polymarket adapter for {self._address}")

    async def shutdown(self) -> None:
        if self._http:
            await self._http.aclose()

    # ── Read: Targets ──

    async def fetch_target_positions(self, address: str) -> list[TargetPosition]:
        return await data_api.fetch_positions(self._http, address)

    async def fetch_target_portfolio_value(self, address: str) -> float:
        return await data_api.fetch_portfolio_value(self._http, address)

    # ── Read: Markets ──

    async def fetch_market(self, market_id: str) -> Market:
        try:
            result = await asyncio.to_thread(
                self._pmxt.get_market, market_id
            )
            status = MarketStatus.OPEN
            if getattr(result, "resolved", False):
                status = MarketStatus.RESOLVED
            elif getattr(result, "closed", False):
                status = MarketStatus.CLOSED

            outcomes = []
            for o in getattr(result, "outcomes", []):
                outcomes.append(getattr(o, "label", str(o)))

            return Market(
                market_id=market_id,
                platform="polymarket",
                question=getattr(result, "question", ""),
                outcomes=outcomes or ["Yes", "No"],
                status=status,
                resolution_outcome=getattr(result, "resolution", None),
            )
        except Exception as e:
            raise TransientError(f"Failed to fetch market {market_id}: {e}") from e

    async def get_price(self, asset_id: str, side: str) -> float:
        try:
            book = await asyncio.to_thread(
                self._pmxt.get_order_book, asset_id
            )
            if side == "buy":
                asks = getattr(book, "asks", [])
                if asks:
                    return float(asks[0].price)
            elif side == "sell":
                bids = getattr(book, "bids", [])
                if bids:
                    return float(bids[0].price)
            # Fallback to midpoint
            bids = getattr(book, "bids", [])
            asks = getattr(book, "asks", [])
            if bids and asks:
                return (float(bids[0].price) + float(asks[0].price)) / 2
            return 0.0
        except Exception as e:
            raise TransientError(f"Failed to get price for {asset_id}: {e}") from e

    # ── Read: Our Wallet ──

    async def get_wallet_state(self) -> WalletState:
        usdc = await blockchain.get_usdc_balance(self._w3, self._address)
        gas = await blockchain.get_matic_balance(self._w3, self._address)
        approvals = await blockchain.check_approvals(self._w3, self._address)
        return WalletState(
            platform="polymarket",
            total_balance=usdc,
            gas_balance=gas,
            approvals_ok=approvals,
        )

    # ── Write: Trading ──

    async def submit_order(self, order: SizedOrder) -> OrderResult:
        now = datetime.now(timezone.utc)
        try:
            result = await asyncio.to_thread(
                self._pmxt.create_and_post_order,
                token_id=order.asset_id,
                price=order.price,
                size=order.size,
                side="BUY" if order.side.value == "BUY" else "SELL",
            )
            return OrderResult(
                order=order,
                success=True,
                order_id=getattr(result, "order_id", str(result)),
                fill_price=order.price,
                fill_size=order.size,
                error=None,
                executed_at=now,
            )
        except Exception as e:
            error_str = str(e)
            if any(kw in error_str.lower() for kw in ["timeout", "429", "5"]):
                raise TransientError(error_str) from e
            raise FatalError(error_str) from e

    async def cancel_order(self, order_id: str) -> bool:
        try:
            await asyncio.to_thread(self._pmxt.cancel_order, order_id)
            return True
        except Exception:
            return False

    async def redeem_if_needed(self, market_id: str, position: OurPosition) -> bool:
        return await blockchain.redeem_positions(self._w3, self._address, market_id)

    # ── Metadata ──

    @property
    def platform_name(self) -> str:
        return "polymarket"

    @property
    def currency_decimals(self) -> int:
        return USDC_DECIMALS
