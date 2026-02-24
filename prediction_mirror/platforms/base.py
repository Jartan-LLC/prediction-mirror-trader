from __future__ import annotations

from abc import ABC, abstractmethod

from prediction_mirror.models.market import Market
from prediction_mirror.models.order import OrderResult, SizedOrder
from prediction_mirror.models.position import OurPosition, TargetPosition
from prediction_mirror.models.wallet import WalletState


class PlatformAdapter(ABC):
    """Abstract interface every platform adapter must implement."""

    # ── Lifecycle ──

    @abstractmethod
    async def initialize(self) -> None:
        """One-time setup: authenticate, set approvals, warm caches."""

    async def shutdown(self) -> None:
        """Clean up connections. Default no-op."""

    # ── Factory ──

    @classmethod
    @abstractmethod
    def from_env(cls) -> PlatformAdapter:
        """Construct from platform-specific env vars."""

    # ── Read: Targets ──

    @abstractmethod
    async def fetch_target_positions(self, address: str) -> list[TargetPosition]:
        ...

    @abstractmethod
    async def fetch_target_portfolio_value(self, address: str) -> float:
        ...

    # ── Read: Markets ──

    @abstractmethod
    async def fetch_market(self, market_id: str) -> Market:
        ...

    @abstractmethod
    async def get_price(self, asset_id: str, side: str) -> float:
        """Get current price. side is 'buy' (best ask) or 'sell' (best bid)."""

    # ── Read: Our Wallet ──

    @abstractmethod
    async def get_wallet_state(self) -> WalletState:
        ...

    # ── Write: Trading ──

    @abstractmethod
    async def submit_order(self, order: SizedOrder) -> OrderResult:
        ...

    async def cancel_order(self, order_id: str) -> bool:
        return False

    async def redeem_if_needed(self, market_id: str, position: OurPosition) -> bool:
        return True

    # ── Metadata ──

    @property
    @abstractmethod
    def platform_name(self) -> str:
        ...

    @property
    @abstractmethod
    def currency_decimals(self) -> int:
        ...
