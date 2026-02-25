from __future__ import annotations

from click.testing import CliRunner

from prediction_mirror.__main__ import cli


class TestTargetsAdd:
    def test_add_target(self, tmp_path):
        db = str(tmp_path / "test.db")
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--db", db, "targets", "add",
            "--label", "Whale",
            "--address", "0xAAA",
            "--platform", "polymarket",
            "--allocation", "50.0",
        ])
        assert result.exit_code == 0
        assert "Added target: Whale" in result.output

    def test_add_duplicate_fails(self, tmp_path):
        db = str(tmp_path / "test.db")
        runner = CliRunner()
        runner.invoke(cli, [
            "--db", db, "targets", "add",
            "--label", "Whale", "--address", "0xAAA",
            "--platform", "polymarket", "--allocation", "50.0",
        ])
        result = runner.invoke(cli, [
            "--db", db, "targets", "add",
            "--label", "Whale", "--address", "0xBBB",
            "--platform", "polymarket", "--allocation", "30.0",
        ])
        assert result.exit_code == 1


class TestTargetsList:
    def test_list_empty(self, tmp_path):
        db = str(tmp_path / "test.db")
        runner = CliRunner()
        result = runner.invoke(cli, ["--db", db, "targets", "list"])
        assert result.exit_code == 0
        assert "Targets" in result.output

    def test_list_shows_added_target(self, tmp_path):
        db = str(tmp_path / "test.db")
        runner = CliRunner()
        runner.invoke(cli, [
            "--db", db, "targets", "add",
            "--label", "Whale", "--address", "0xAAA",
            "--platform", "polymarket", "--allocation", "50.0",
        ])
        result = runner.invoke(cli, ["--db", db, "targets", "list"])
        assert "Whale" in result.output
        assert "50.0" in result.output


class TestTargetsEnableDisable:
    def _add_target(self, runner, db):
        runner.invoke(cli, [
            "--db", db, "targets", "add",
            "--label", "Whale", "--address", "0xAAA",
            "--platform", "polymarket", "--allocation", "50.0",
        ])

    def test_disable(self, tmp_path):
        db = str(tmp_path / "test.db")
        runner = CliRunner()
        self._add_target(runner, db)
        result = runner.invoke(cli, ["--db", db, "targets", "disable", "Whale"])
        assert result.exit_code == 0
        assert "Disabled" in result.output

    def test_enable(self, tmp_path):
        db = str(tmp_path / "test.db")
        runner = CliRunner()
        self._add_target(runner, db)
        runner.invoke(cli, ["--db", db, "targets", "disable", "Whale"])
        result = runner.invoke(cli, ["--db", db, "targets", "enable", "Whale"])
        assert result.exit_code == 0
        assert "Enabled" in result.output

    def test_enable_missing_fails(self, tmp_path):
        db = str(tmp_path / "test.db")
        runner = CliRunner()
        result = runner.invoke(cli, ["--db", db, "targets", "enable", "Ghost"])
        assert result.exit_code == 1


class TestTargetsRemove:
    def test_remove(self, tmp_path):
        db = str(tmp_path / "test.db")
        runner = CliRunner()
        runner.invoke(cli, [
            "--db", db, "targets", "add",
            "--label", "Whale", "--address", "0xAAA",
            "--platform", "polymarket", "--allocation", "50.0",
        ])
        result = runner.invoke(cli, ["--db", db, "targets", "remove", "Whale"])
        assert result.exit_code == 0
        assert "Removed" in result.output

    def test_remove_missing_fails(self, tmp_path):
        db = str(tmp_path / "test.db")
        runner = CliRunner()
        result = runner.invoke(cli, ["--db", db, "targets", "remove", "Ghost"])
        assert result.exit_code == 1


class TestTargetsSetAllocation:
    def test_set_allocation(self, tmp_path):
        db = str(tmp_path / "test.db")
        runner = CliRunner()
        runner.invoke(cli, [
            "--db", db, "targets", "add",
            "--label", "Whale", "--address", "0xAAA",
            "--platform", "polymarket", "--allocation", "50.0",
        ])
        result = runner.invoke(cli, ["--db", db, "targets", "set-allocation", "Whale", "30.0"])
        assert result.exit_code == 0
        assert "30.0%" in result.output


class TestHelpOutput:
    def test_top_level_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "run" in result.output
        assert "settings" in result.output
        assert "targets" in result.output
