from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from prediction_mirror.models.market import MarketStatus
from prediction_mirror.models.order import OrderSide, SizedOrder
from prediction_mirror.models.position import OurPosition
from prediction_mirror.models.signal import Signal, SignalType
from prediction_mirror.models.target import TargetConfig
from prediction_mirror.platforms.errors import FatalError, TransientError
from prediction_mirror.platforms.polymarket.adapter import PolymarketAdapter
from prediction_mirror.platforms.polymarket.config import DATA_API_URL
from prediction_mirror.platforms.polymarket.data_api import fetch_positions, fetch_portfolio_value

NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


# ── Fixtures ──


@pytest.fixture
def mock_pmxt():
    client = MagicMock()
    client.fetch_market = MagicMock()
    client.fetch_order_book = MagicMock()
    client.create_order = MagicMock()
    client.cancel_order = MagicMock()
    return client


@pytest.fixture
def mock_w3():
    w3 = MagicMock()
    w3.eth.get_balance = MagicMock(return_value=500_000_000_000_000_000)  # 0.5 MATIC
    w3.from_wei = MagicMock(return_value=0.5)

    # USDC contract mock
    usdc_contract = MagicMock()
    usdc_contract.functions.balanceOf.return_value.call.return_value = 1_000_000_000  # 1000 USDC
    usdc_contract.functions.allowance.return_value.call.return_value = 2**256 - 1  # max approval

    w3.eth.contract = MagicMock(return_value=usdc_contract)

    # Account derivation
    account = MagicMock()
    account.address = "0xTestAddress123"
    w3.eth.account.from_key = MagicMock(return_value=account)
    return w3


@pytest.fixture
def adapter(mock_pmxt, mock_w3):
    return PolymarketAdapter(
        private_key="0x" + "ab" * 32,
        rpc_url="https://polygon-rpc.com",
        pmxt_client=mock_pmxt,
        w3=mock_w3,
        http_client=httpx.AsyncClient(),
    )


@pytest.fixture
def signal():
    target = TargetConfig(
        label="Whale", platform="polymarket", address="0xAAA", allocation_pct=50.0
    )
    return Signal(
        signal_type=SignalType.BUY,
        target=target,
        platform="polymarket",
        market_id="cond_1",
        asset_id="tok_1",
        outcome="Yes",
        target_delta=10.0,
        target_prev_size=90.0,
        target_price=0.55,
        detected_at=NOW,
    )


# ── Data API Tests ──


class TestDataApi:
    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_positions_success(self):
        respx.get(f"{DATA_API_URL}/positions").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "conditionId": "cond_abc",
                        "asset": "tok_yes",
                        "outcome": "Yes",
                        "size": "100.0",
                        "avgPrice": "0.55",
                        "curPrice": "0.60",
                    },
                    {
                        "conditionId": "cond_abc",
                        "asset": "tok_no",
                        "outcome": "No",
                        "size": "0",
                        "avgPrice": "0.45",
                        "curPrice": "0.40",
                    },
                ],
            )
        )
        async with httpx.AsyncClient() as client:
            positions = await fetch_positions(client, "0xTarget")

        assert len(positions) == 1  # zero-size filtered out
        assert positions[0].market_id == "cond_abc"
        assert positions[0].asset_id == "tok_yes"
        assert positions[0].size == 100.0

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_positions_rate_limited(self):
        respx.get(f"{DATA_API_URL}/positions").mock(
            return_value=httpx.Response(429, text="Too many requests")
        )
        async with httpx.AsyncClient() as client:
            with pytest.raises(TransientError, match="429"):
                await fetch_positions(client, "0xTarget")

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_positions_server_error(self):
        respx.get(f"{DATA_API_URL}/positions").mock(
            return_value=httpx.Response(500, text="Internal error")
        )
        async with httpx.AsyncClient() as client:
            with pytest.raises(TransientError, match="500"):
                await fetch_positions(client, "0xTarget")

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_positions_client_error(self):
        respx.get(f"{DATA_API_URL}/positions").mock(
            return_value=httpx.Response(400, text="Bad request")
        )
        async with httpx.AsyncClient() as client:
            with pytest.raises(FatalError, match="400"):
                await fetch_positions(client, "0xTarget")

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_positions_timeout(self):
        respx.get(f"{DATA_API_URL}/positions").mock(side_effect=httpx.TimeoutException("timeout"))
        async with httpx.AsyncClient() as client:
            with pytest.raises(TransientError, match="timeout"):
                await fetch_positions(client, "0xTarget")

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_portfolio_value(self):
        respx.get(f"{DATA_API_URL}/positions").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"conditionId": "c1", "asset": "t1", "outcome": "Yes",
                     "size": "10.0", "avgPrice": "0.5", "curPrice": "0.6"},
                    {"conditionId": "c2", "asset": "t2", "outcome": "No",
                     "size": "20.0", "avgPrice": "0.3", "curPrice": "0.4"},
                ],
            )
        )
        async with httpx.AsyncClient() as client:
            value = await fetch_portfolio_value(client, "0xTarget")

        assert value == pytest.approx(10.0 * 0.6 + 20.0 * 0.4)


# ── Adapter Tests ──


class TestAdapterInit:
    @pytest.mark.asyncio
    async def test_initialize(self, adapter, mock_w3):
        await adapter.initialize()
        mock_w3.eth.account.from_key.assert_called_once()

    def test_from_env_missing_key(self, monkeypatch):
        monkeypatch.delenv("POLYMARKET_PRIVATE_KEY", raising=False)
        with pytest.raises(EnvironmentError, match="POLYMARKET_PRIVATE_KEY"):
            PolymarketAdapter.from_env()

    @pytest.mark.asyncio
    async def test_metadata(self, adapter):
        assert adapter.platform_name == "polymarket"
        assert adapter.currency_decimals == 6


class TestAdapterMarkets:
    @pytest.mark.asyncio
    async def test_fetch_market(self, adapter, mock_pmxt):
        mock_pmxt.fetch_market.return_value = SimpleNamespace(
            question="Will BTC hit 100k?",
            outcomes=[SimpleNamespace(label="Yes"), SimpleNamespace(label="No")],
            resolved=False,
            closed=False,
        )
        await adapter.initialize()
        market = await adapter.fetch_market("cond_1")
        assert market.question == "Will BTC hit 100k?"
        assert market.status == MarketStatus.OPEN
        assert market.outcomes == ["Yes", "No"]

    @pytest.mark.asyncio
    async def test_fetch_market_resolved(self, adapter, mock_pmxt):
        mock_pmxt.fetch_market.return_value = SimpleNamespace(
            question="Resolved?",
            outcomes=[],
            resolved=True,
            closed=False,
            resolution="Yes",
        )
        await adapter.initialize()
        market = await adapter.fetch_market("cond_1")
        assert market.status == MarketStatus.RESOLVED

    @pytest.mark.asyncio
    async def test_get_price_buy(self, adapter, mock_pmxt):
        mock_pmxt.fetch_order_book.return_value = SimpleNamespace(
            bids=[SimpleNamespace(price=0.54)],
            asks=[SimpleNamespace(price=0.56)],
        )
        await adapter.initialize()
        price = await adapter.get_price("tok_1", "buy")
        assert price == 0.56  # best ask

    @pytest.mark.asyncio
    async def test_get_price_sell(self, adapter, mock_pmxt):
        mock_pmxt.fetch_order_book.return_value = SimpleNamespace(
            bids=[SimpleNamespace(price=0.54)],
            asks=[SimpleNamespace(price=0.56)],
        )
        await adapter.initialize()
        price = await adapter.get_price("tok_1", "sell")
        assert price == 0.54  # best bid

    @pytest.mark.asyncio
    async def test_get_price_midpoint_fallback(self, adapter, mock_pmxt):
        mock_pmxt.fetch_order_book.return_value = SimpleNamespace(
            bids=[SimpleNamespace(price=0.50)],
            asks=[SimpleNamespace(price=0.60)],
        )
        await adapter.initialize()
        # Side is "buy" but no asks — only bids have data.
        # Actually both have data, so let's test empty asks for buy:
        mock_pmxt.fetch_order_book.return_value = SimpleNamespace(
            bids=[SimpleNamespace(price=0.50)],
            asks=[],
        )
        price = await adapter.get_price("tok_1", "buy")
        # Falls through to midpoint check. Only bids exist, no asks => 0.0 fallback
        assert price == 0.0


class TestAdapterTrading:
    @pytest.mark.asyncio
    async def test_submit_order_success(self, adapter, mock_pmxt, signal):
        mock_pmxt.create_order.return_value = SimpleNamespace(id="ord_123")
        await adapter.initialize()

        order = SizedOrder(
            signal=signal,
            side=OrderSide.BUY,
            asset_id="tok_1",
            price=0.55,
            size=5.0,
            usd_amount=2.75,
            dry_run=False,
        )
        result = await adapter.submit_order(order)
        assert result.success is True
        assert result.order_id == "ord_123"

    @pytest.mark.asyncio
    async def test_submit_order_fatal_error(self, adapter, mock_pmxt, signal):
        mock_pmxt.create_order.side_effect = Exception("insufficient funds")
        await adapter.initialize()

        order = SizedOrder(
            signal=signal,
            side=OrderSide.BUY,
            asset_id="tok_1",
            price=0.55,
            size=5.0,
            usd_amount=2.75,
            dry_run=False,
        )
        with pytest.raises(FatalError, match="insufficient funds"):
            await adapter.submit_order(order)

    @pytest.mark.asyncio
    async def test_submit_order_transient_error(self, adapter, mock_pmxt, signal):
        mock_pmxt.create_order.side_effect = Exception("timeout connecting")
        await adapter.initialize()

        order = SizedOrder(
            signal=signal,
            side=OrderSide.BUY,
            asset_id="tok_1",
            price=0.55,
            size=5.0,
            usd_amount=2.75,
            dry_run=False,
        )
        with pytest.raises(TransientError, match="timeout"):
            await adapter.submit_order(order)


class TestAdapterWallet:
    @pytest.mark.asyncio
    async def test_get_wallet_state(self, adapter):
        await adapter.initialize()
        wallet = await adapter.get_wallet_state()
        assert wallet.platform == "polymarket"
        assert wallet.total_balance == 1000.0
        assert wallet.gas_balance == 0.5
        assert wallet.approvals_ok is True


# ── Redemption Tests ──


TEST_KEY = "0x" + "ab" * 32


@pytest.fixture
def redeem_w3(mock_w3):
    """mock_w3 with a ConditionalTokens contract wired for a successful redemption."""
    ct_contract = MagicMock()
    ct_contract.functions.redeemPositions.return_value.build_transaction.return_value = {
        "from": "0xTestAddress123",
        "gas": 300_000,
        "nonce": 7,
    }
    mock_w3.eth.contract = MagicMock(return_value=ct_contract)
    mock_w3.eth.get_transaction_count = MagicMock(return_value=7)
    mock_w3.eth.account.sign_transaction = MagicMock(
        return_value=SimpleNamespace(raw_transaction=b"\xde\xad")
    )
    mock_w3.eth.send_raw_transaction = MagicMock(return_value=MagicMock())
    mock_w3.eth.wait_for_transaction_receipt = MagicMock(return_value={"status": 1})
    return mock_w3


@pytest.fixture
def redeem_adapter(mock_pmxt, redeem_w3):
    return PolymarketAdapter(
        private_key=TEST_KEY,
        rpc_url="https://polygon-rpc.com",
        pmxt_client=mock_pmxt,
        w3=redeem_w3,
        http_client=httpx.AsyncClient(),
    )


class TestAdapterRedemption:
    @pytest.mark.asyncio
    async def test_signs_with_real_key_material(self, redeem_adapter, redeem_w3):
        await redeem_adapter.initialize()
        pos = OurPosition(
            market_id="0x" + "cd" * 32,
            asset_id="tok_1",
            platform="polymarket",
            outcome="Yes",
            size=10.0,
            avg_entry_price=0.5,
            total_cost=5.0,
            realized_pnl=0.0,
            source_target="Whale",
            dry_run=False,
            updated_at=NOW,
        )

        assert await redeem_adapter.redeem_if_needed(pos.market_id, pos) is True

        _tx, key = redeem_w3.eth.account.sign_transaction.call_args[0]
        assert key is not None
        assert key == TEST_KEY

    @pytest.mark.asyncio
    async def test_transaction_carries_a_nonce(self, redeem_adapter, redeem_w3):
        await redeem_adapter.initialize()
        from prediction_mirror.platforms.polymarket.blockchain import redeem_positions

        await redeem_positions(redeem_w3, "0xTestAddress123", "0x" + "cd" * 32, TEST_KEY)

        ct = redeem_w3.eth.contract.return_value
        build = ct.functions.redeemPositions.return_value.build_transaction
        assert build.call_args[0][0]["nonce"] == 7

    @pytest.mark.asyncio
    async def test_reverted_receipt_returns_false(self, redeem_adapter, redeem_w3):
        redeem_w3.eth.wait_for_transaction_receipt = MagicMock(
            return_value={"status": 0}
        )
        from prediction_mirror.platforms.polymarket.blockchain import redeem_positions

        result = await redeem_positions(
            redeem_w3, "0xTestAddress123", "0x" + "cd" * 32, TEST_KEY
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_key_never_reaches_the_error_message(self, redeem_w3):
        """A signing library that echoed the key must not leak it through FatalError."""
        redeem_w3.eth.account.sign_transaction = MagicMock(
            side_effect=ValueError(f"bad key: {TEST_KEY}")
        )
        from prediction_mirror.platforms.polymarket.blockchain import redeem_positions

        with pytest.raises(FatalError) as exc:
            await redeem_positions(
                redeem_w3, "0xTestAddress123", "0x" + "cd" * 32, TEST_KEY
            )

        message = str(exc.value)
        assert TEST_KEY not in message
        assert "ab" * 32 not in message
        assert "[REDACTED]" in message


# ── Registry Tests ──


class TestAdapterRegistry:
    def test_polymarket_registered(self):
        # Importing polymarket/__init__.py triggers registration
        import prediction_mirror.platforms.polymarket  # noqa: F401
        from prediction_mirror.platforms import get_adapter_class

        cls = get_adapter_class("polymarket")
        assert cls is PolymarketAdapter

    def test_unknown_platform_raises(self):
        from prediction_mirror.platforms import get_adapter_class

        with pytest.raises(KeyError, match="Unknown platform"):
            get_adapter_class("nonexistent")


# ── Error Taxonomy Tests ──


class TestErrors:
    def test_hierarchy(self):
        assert issubclass(TransientError, Exception)
        assert issubclass(FatalError, Exception)
        from prediction_mirror.platforms.errors import PlatformError

        assert issubclass(TransientError, PlatformError)
        assert issubclass(FatalError, PlatformError)
