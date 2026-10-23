"""Unit tests for the CloudFirst Aid CLI commands."""

from __future__ import annotations

import pytest

from cloudfirst_aid.cli import main


def test_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify --help exits cleanly with status 0 and outputs usage instructions."""
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "CloudFirst Aid" in captured.out
    assert "Available subcommands" in captured.out


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify --version returns version number."""
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "0.1.0" in captured.out


def test_cli_list(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify list command returns table with scenarios."""
    exit_code = main(["list"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "CFA-001" in captured.out
    assert "CFA-010" in captured.out
    assert "CFA-030" in captured.out


def test_cli_list_filter_category(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify list filtering by category."""
    exit_code = main(["list", "-c", "linux"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "CFA-010" in captured.out
    assert "CFA-001" not in captured.out  # ec2 shouldn't appear


def test_cli_show_valid(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify show command displays scenario details."""
    exit_code = main(["show", "CFA-001"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "[CFA-001]" in captured.out
    assert "EC2 SSH Connection Times Out" in captured.out
    assert "RECOMMENDED INVESTIGATION SEQUENCE" in captured.out


def test_cli_show_unknown(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify show command fails gracefully for nonexistent ID."""
    exit_code = main(["show", "CFA-999"])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "not found" in captured.err.lower()


def test_cli_validate(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify validate command succeeds on valid catalog."""
    exit_code = main(["validate"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "OK: Catalog is structurally valid." in captured.out


def test_cli_triage(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify triage runs deterministic rule evaluation."""
    exit_code = main(["triage", "CFA-001"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Diagnostic Findings" in captured.out
    assert "OBSERVED" in captured.out


def test_cli_report_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify report outputs markdown to stdout when no output file specified."""
    exit_code = main(["report", "CFA-010"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "# Incident Investigation Report: CFA-010" in captured.out
    assert "## 2. Diagnostic Evidence & Provenance" in captured.out
    assert "CONFIRMED" in captured.out
