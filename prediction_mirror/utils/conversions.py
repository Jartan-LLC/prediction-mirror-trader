from __future__ import annotations

USDC_DECIMALS = 6
USDC_FACTOR = 10**USDC_DECIMALS


def usdc_to_raw(amount: float) -> int:
    """Convert a human-readable USDC amount to raw integer (6 decimals)."""
    return int(round(amount * USDC_FACTOR))


def raw_to_usdc(raw: int) -> float:
    """Convert raw USDC integer to human-readable float."""
    return raw / USDC_FACTOR


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp value to [min_val, max_val]."""
    return max(min_val, min(value, max_val))
