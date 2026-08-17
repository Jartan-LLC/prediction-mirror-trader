from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from click.testing import CliRunner

from prediction_mirror.__main__ import cli
from prediction_mirror.platforms.polymarket.adapter import PolymarketAdapter

TEST_KEY = "0x" + "ab" * 32


def _add_target(runner, db):
    result = runner.invoke(cli, [
        "--db", db, "targets", "add",
        "--label", "Whale",
        "--address", "0xAAA",
        "--platform", "polymarket",
        "--allocation", "50.0",
    ])
    assert result.exit_code == 0


@pytest.fixture
def failing_adapter(monkeypatch):
    """An adapter whose real initialize() hits a library error carrying the key."""
    w3 = MagicMock()
    w3.eth.account.from_key = MagicMock(
        side_effect=ValueError(f"invalid key material: {TEST_KEY}")
    )
    adapter = PolymarketAdapter(
        private_key=TEST_KEY,
        rpc_url="https://polygon-rpc.com",
        pmxt_client=MagicMock(),
        w3=w3,
        http_client=httpx.AsyncClient(),
    )
    monkeypatch.setattr(
        PolymarketAdapter, "from_env", classmethod(lambda cls: adapter)
    )
    return adapter


class TestRunStartupFailure:
    """A failed adapter startup must not print a traceback out of `__main__`.

    `initialize()` is awaited inside `_run()`, which `asyncio.run` drives with
    only KeyboardInterrupt caught around it. Anything else escaping there
    reaches the default excepthook, which renders every frame and every
    __cause__ — and the private key is in scope at both initialize() boundaries.
    """

    def test_startup_failure_exits_without_a_traceback(self, tmp_path, failing_adapter):
        db = str(tmp_path / "test.db")
        runner = CliRunner()
        _add_target(runner, db)

        result = runner.invoke(cli, ["--db", db, "run", "--no-dashboard"])

        assert result.exit_code == 1
        assert "Failed to initialize polymarket adapter" in result.output
        assert "Traceback" not in result.output

    def test_startup_failure_does_not_print_the_key(self, tmp_path, failing_adapter):
        db = str(tmp_path / "test.db")
        runner = CliRunner()
        _add_target(runner, db)

        result = runner.invoke(cli, ["--db", db, "run", "--no-dashboard"])

        # Collapse whitespace first: rich wraps long lines, and a key split
        # across two of them would slip past a naive substring check.
        unwrapped = "".join(result.output.split())
        assert "ab" * 32 not in unwrapped
        assert "[REDACTED]" in result.output

    def test_the_cause_chain_is_not_reachable_from_main(self, tmp_path, failing_adapter):
        """What escapes `_run()` must carry nothing for the excepthook to walk."""
        db = str(tmp_path / "test.db")
        runner = CliRunner()
        _add_target(runner, db)

        result = runner.invoke(cli, ["--db", db, "run", "--no-dashboard"])

        assert isinstance(result.exception, SystemExit)
        assert result.exception.__cause__ is None
        assert result.exception.__suppress_context__ is True
