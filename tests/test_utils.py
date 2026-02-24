from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest

from prediction_mirror.utils.conversions import (
    USDC_DECIMALS,
    clamp,
    raw_to_usdc,
    usdc_to_raw,
)
from prediction_mirror.utils.formatting import fmt_address, fmt_pct, fmt_timestamp, fmt_usd
from prediction_mirror.utils.log import configure_logging, get_logger


# ── Formatting ──


class TestFmtUsd:
    def test_positive(self):
        assert fmt_usd(1234.56) == "$1,234.56"

    def test_zero(self):
        assert fmt_usd(0) == "$0.00"

    def test_negative(self):
        assert fmt_usd(-42.10) == "-$42.10"

    def test_large_number(self):
        assert fmt_usd(1_000_000.00) == "$1,000,000.00"

    def test_small_fraction(self):
        assert fmt_usd(0.01) == "$0.01"

    def test_rounds_to_cents(self):
        assert fmt_usd(1.999) == "$2.00"


class TestFmtPct:
    def test_whole(self):
        assert fmt_pct(50.0) == "50.0%"

    def test_fractional(self):
        assert fmt_pct(33.3) == "33.3%"

    def test_zero(self):
        assert fmt_pct(0.0) == "0.0%"

    def test_hundred(self):
        assert fmt_pct(100.0) == "100.0%"


class TestFmtAddress:
    def test_long_address(self):
        addr = "0xABCDEF1234567890abcdef1234567890ABCDEF12"
        result = fmt_address(addr)
        # Default chars=6: "0xABCDEF" (8 chars) + "..." + "CDEF12" (6 chars)
        assert result == "0xABCDEF...CDEF12"

    def test_short_address_unchanged(self):
        addr = "0xABCD"
        assert fmt_address(addr) == "0xABCD"

    def test_custom_chars(self):
        addr = "0xABCDEF1234567890abcdef1234567890ABCDEF12"
        result = fmt_address(addr, chars=4)
        assert result == "0xABCD...EF12"


class TestFmtTimestamp:
    def test_formatting(self):
        dt = datetime(2025, 1, 15, 14, 5, 32, tzinfo=timezone.utc)
        assert fmt_timestamp(dt) == "2025-01-15 14:05:32"


# ── Conversions ──


class TestUsdcConversions:
    def test_decimals_constant(self):
        assert USDC_DECIMALS == 6

    def test_to_raw(self):
        assert usdc_to_raw(1.0) == 1_000_000

    def test_to_raw_fractional(self):
        assert usdc_to_raw(0.5) == 500_000

    def test_to_raw_rounds(self):
        # 1.0000005 should round to 1000001
        assert usdc_to_raw(1.0000005) == 1_000_001

    def test_from_raw(self):
        assert raw_to_usdc(1_000_000) == 1.0

    def test_from_raw_fractional(self):
        assert raw_to_usdc(500_000) == 0.5

    def test_roundtrip(self):
        original = 123.456789
        assert raw_to_usdc(usdc_to_raw(original)) == pytest.approx(original, abs=1e-6)


class TestClamp:
    def test_within_range(self):
        assert clamp(5.0, 0.0, 10.0) == 5.0

    def test_below_min(self):
        assert clamp(-1.0, 0.0, 10.0) == 0.0

    def test_above_max(self):
        assert clamp(15.0, 0.0, 10.0) == 10.0

    def test_at_min(self):
        assert clamp(0.0, 0.0, 10.0) == 0.0

    def test_at_max(self):
        assert clamp(10.0, 0.0, 10.0) == 10.0


# ── Logging ──


class TestLogging:
    def test_get_logger_prefix(self):
        logger = get_logger("monitor")
        assert logger.name == "prediction_mirror.monitor"

    def test_configure_logging(self, tmp_path, monkeypatch):
        # Avoid polluting the working directory with log files
        monkeypatch.chdir(tmp_path)
        configure_logging("DEBUG")
        root = logging.getLogger("prediction_mirror")
        assert root.level == logging.DEBUG
        assert len(root.handlers) >= 2  # console + file

    def test_configure_logging_idempotent(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # Reset handlers for clean test
        root = logging.getLogger("prediction_mirror")
        root.handlers.clear()
        configure_logging("INFO")
        count = len(root.handlers)
        configure_logging("INFO")
        assert len(root.handlers) == count  # no duplicates


# ── Re-exports ──


class TestReExports:
    def test_all_utils_importable(self):
        from prediction_mirror.utils import (
            USDC_DECIMALS,
            clamp,
            configure_logging,
            fmt_address,
            fmt_pct,
            fmt_timestamp,
            fmt_usd,
            get_logger,
            raw_to_usdc,
            usdc_to_raw,
        )

        assert all(
            callable(fn)
            for fn in [
                clamp,
                configure_logging,
                fmt_address,
                fmt_pct,
                fmt_timestamp,
                fmt_usd,
                get_logger,
                raw_to_usdc,
                usdc_to_raw,
            ]
        )
