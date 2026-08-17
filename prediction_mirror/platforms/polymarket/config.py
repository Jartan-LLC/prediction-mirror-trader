from __future__ import annotations

import os
import re

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


def normalize_private_key(key: str) -> str:
    """Return the one canonical form of a key: trimmed, lower-case hex.

    Signing, redaction and comparison must all see the same string. A key
    carrying a stray newline or upper-case hex signs fine but defeats the
    substring match in `redact_key`, so it is normalized once, at load.
    """
    return key.strip().lower()


def redact_key(message: str, private_key: str) -> str:
    """Strip private key material out of a message before it is raised or logged.

    web3.py and eth-account do not echo the key in their current error strings,
    but that is not a guarantee they keep; this makes it one on our side.
    Matching is case-insensitive and prefix-agnostic so a key that reached us
    un-normalized is still caught.
    """
    if not private_key:
        return message
    bare = private_key.strip()
    if bare[:2].lower() == "0x":
        bare = bare[2:]
    if not bare:
        return message
    return re.sub(re.escape(bare), "[REDACTED]", message, flags=re.IGNORECASE)


def load_private_key() -> str:
    key = normalize_private_key(os.environ.get("POLYMARKET_PRIVATE_KEY", ""))
    if not key:
        raise EnvironmentError(
            "POLYMARKET_PRIVATE_KEY not set. See docs/configuration.md"
        )
    return key


def load_rpc_url() -> str:
    return os.environ.get(
        "POLYMARKET_RPC_URL", "https://polygon-rpc.com"
    )
