from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WalletState:
    platform: str
    total_balance: float
    gas_balance: float | None
    approvals_ok: bool
