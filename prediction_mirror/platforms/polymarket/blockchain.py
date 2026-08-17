from __future__ import annotations

import asyncio
from typing import Any

import logging

from prediction_mirror.platforms.errors import FatalError, TransientError
from prediction_mirror.platforms.polymarket.config import (
    CONDITIONAL_TOKENS,
    CTF_EXCHANGE,
    USDC_ADDRESS,
    USDC_DECIMALS,
    redact_key,
)
logger = logging.getLogger(__name__)

# Minimal ABIs for the operations we need
ERC20_ABI = [
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
    {
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
    {
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
]

CONDITIONAL_TOKENS_ABI = [
    {
        "inputs": [
            {"name": "collateralToken", "type": "address"},
            {"name": "parentCollectionId", "type": "bytes32"},
            {"name": "conditionId", "type": "bytes32"},
            {"name": "indexSets", "type": "uint256[]"},
        ],
        "name": "redeemPositions",
        "outputs": [],
        "type": "function",
    },
]


async def get_matic_balance(w3: Any, address: str) -> float:
    """Get native MATIC/POL balance in ether units."""
    try:
        balance_wei = await asyncio.to_thread(w3.eth.get_balance, address)
        return float(w3.from_wei(balance_wei, "ether"))
    except Exception as e:
        raise TransientError(f"Failed to get MATIC balance: {e}") from e


async def get_usdc_balance(w3: Any, address: str) -> float:
    """Get USDC.e balance in human-readable units."""
    try:
        usdc = w3.eth.contract(address=USDC_ADDRESS, abi=ERC20_ABI)
        raw = await asyncio.to_thread(usdc.functions.balanceOf(address).call)
        return raw / (10**USDC_DECIMALS)
    except Exception as e:
        raise TransientError(f"Failed to get USDC balance: {e}") from e


async def check_approvals(w3: Any, owner: str) -> bool:
    """Check if USDC is approved for CTF Exchange."""
    try:
        usdc = w3.eth.contract(address=USDC_ADDRESS, abi=ERC20_ABI)
        allowance = await asyncio.to_thread(
            usdc.functions.allowance(owner, CTF_EXCHANGE).call
        )
        return allowance > 0
    except Exception as e:
        raise TransientError(f"Failed to check approvals: {e}") from e


async def redeem_positions(
    w3: Any, address: str, condition_id: str, private_key: str
) -> bool:
    """Redeem resolved positions via ConditionalTokens contract."""
    try:
        ct = w3.eth.contract(address=CONDITIONAL_TOKENS, abi=CONDITIONAL_TOKENS_ABI)
        # build_transaction fills the fee fields and chainId, but not the nonce —
        # only the standalone fill_nonce helper does, and it is not on this path.
        nonce = await asyncio.to_thread(
            w3.eth.get_transaction_count, address, "pending"
        )
        # Build the transaction
        tx = ct.functions.redeemPositions(
            USDC_ADDRESS,
            b"\x00" * 32,  # parentCollectionId (root)
            bytes.fromhex(condition_id.replace("0x", "")),
            [1, 2],  # indexSets for binary outcomes
        ).build_transaction({
            "from": address,
            "gas": 300_000,
            "nonce": nonce,
        })
        # Sign and send
        signed = await asyncio.to_thread(
            w3.eth.account.sign_transaction, tx, private_key
        )
        tx_hash = await asyncio.to_thread(w3.eth.send_raw_transaction, signed.raw_transaction)
        receipt = await asyncio.to_thread(w3.eth.wait_for_transaction_receipt, tx_hash, timeout=60)
        success = receipt["status"] == 1
        if success:
            logger.info(f"Redeemed {condition_id}: tx={tx_hash.hex()}")
        else:
            logger.warning(f"Redemption reverted for {condition_id}: tx={tx_hash.hex()}")
        return success
    except Exception as e:
        raise FatalError(
            f"Redemption failed for {condition_id}: "
            f"{redact_key(str(e), private_key)}"
        ) from e
