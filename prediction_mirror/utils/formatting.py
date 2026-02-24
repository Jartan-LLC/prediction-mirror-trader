from __future__ import annotations

from datetime import datetime


def fmt_usd(amount: float) -> str:
    """Format a dollar amount: $1,234.56"""
    if amount < 0:
        return f"-${abs(amount):,.2f}"
    return f"${amount:,.2f}"


def fmt_pct(value: float) -> str:
    """Format a percentage: 50.0%"""
    return f"{value:.1f}%"


def fmt_address(address: str, chars: int = 6) -> str:
    """Shorten an address: 0xAbCd...eF12"""
    if len(address) <= chars * 2 + 2:
        return address
    return f"{address[:chars + 2]}...{address[-chars:]}"


def fmt_timestamp(dt: datetime) -> str:
    """Format a datetime for display: 2024-01-15 14:05:32"""
    return dt.strftime("%Y-%m-%d %H:%M:%S")
