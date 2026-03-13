"""Tests for ids.py — parser protocol and make_partition_keys."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from improv.ids import ImageIdParts, make_partition_keys


def test_alpha_parser_matches(alpha_parser):
    parts = alpha_parser.parse("ALPHA_20240115T120000_001")
    assert parts is not None
    assert parts.instrument == "ALPHA"
    assert parts.timestamp == datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


def test_alpha_parser_no_match(alpha_parser):
    assert alpha_parser.parse("BETA_20240115T120000_001") is None
    assert alpha_parser.parse("not-an-id") is None


def test_beta_parser_matches(beta_parser):
    parts = beta_parser.parse("BETA-20240115T120000-001")
    assert parts is not None
    assert parts.instrument == "BETA"
    assert parts.timestamp == datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


def test_beta_parser_no_match(beta_parser):
    assert beta_parser.parse("ALPHA_20240115T120000_001") is None


def test_make_partition_keys_alpha(parsers):
    keys = make_partition_keys("ALPHA_20240115T120000_001", parsers)
    assert keys == {"instrument": "ALPHA", "year": 2024, "month": 1}


def test_make_partition_keys_beta(parsers):
    keys = make_partition_keys("BETA-20240215T060000-002", parsers)
    assert keys == {"instrument": "BETA", "year": 2024, "month": 2}


def test_make_partition_keys_hint_fallback(parsers):
    keys = make_partition_keys("UNKNOWN_SOMETHING_999", parsers, instrument_hint="GAMMA")
    assert keys == {"instrument": "GAMMA"}
    assert "year" not in keys
    assert "month" not in keys


def test_make_partition_keys_raises_without_hint(parsers):
    with pytest.raises(ValueError, match="no parser matched"):
        make_partition_keys("UNKNOWN_SOMETHING_999", parsers)


def test_make_partition_keys_first_parser_wins(alpha_parser):
    # Only alpha parser registered — beta IDs should fall back to hint
    keys = make_partition_keys(
        "BETA-20240115T120000-001", [alpha_parser], instrument_hint="HINT"
    )
    assert keys["instrument"] == "HINT"
