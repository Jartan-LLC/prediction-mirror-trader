from __future__ import annotations

from click.testing import CliRunner

from prediction_mirror.__main__ import cli


class TestSettingsList:
    def test_list_shows_all_settings(self, tmp_path):
        db = str(tmp_path / "test.db")
        runner = CliRunner()
        result = runner.invoke(cli, ["--db", db, "settings", "list"])
        assert result.exit_code == 0
        assert "poll_interval_seconds" in result.output
        assert "dry_run" in result.output

    def test_list_shows_default_values(self, tmp_path):
        db = str(tmp_path / "test.db")
        runner = CliRunner()
        result = runner.invoke(cli, ["--db", db, "settings", "list"])
        assert "true" in result.output  # dry_run default


class TestSettingsSet:
    def test_set_valid_setting(self, tmp_path):
        db = str(tmp_path / "test.db")
        runner = CliRunner()
        result = runner.invoke(cli, ["--db", db, "settings", "set", "dry_run", "false"])
        assert result.exit_code == 0
        assert "Set dry_run = false" in result.output

    def test_set_reflects_in_list(self, tmp_path):
        db = str(tmp_path / "test.db")
        runner = CliRunner()
        runner.invoke(cli, ["--db", db, "settings", "set", "max_order_usd", "100.0"])
        result = runner.invoke(cli, ["--db", db, "settings", "list"])
        assert "100.0" in result.output

    def test_set_unknown_key(self, tmp_path):
        db = str(tmp_path / "test.db")
        runner = CliRunner()
        result = runner.invoke(cli, ["--db", db, "settings", "set", "bogus", "value"])
        assert result.exit_code == 1
        assert "Unknown setting" in result.output

    def test_set_invalid_value(self, tmp_path):
        db = str(tmp_path / "test.db")
        runner = CliRunner()
        result = runner.invoke(cli, ["--db", db, "settings", "set", "dry_run", "maybe"])
        assert result.exit_code == 1
