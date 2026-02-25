from __future__ import annotations

import os

# ── Public API URLs ──
DATA_API_URL = "https://data-api.polymarket.com"
GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"

# ── Polygon chain (137) contract addresses ──
CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
CONDITIONAL_TOKENS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
CHAIN_ID = 137

# ── USDC on Polygon has 6 decimals ──
USDC_DECIMALS = 6


def load_private_key() -> str:
    key = os.environ.get("POLYMARKET_PRIVATE_KEY", "")
    if not key:
        raise EnvironmentError(
            "POLYMARKET_PRIVATE_KEY not set. See docs/configuration.md"
        )
    return key


def load_rpc_url() -> str:
    return os.environ.get(
        "POLYMARKET_RPC_URL", "https://polygon-rpc.com"
    )
