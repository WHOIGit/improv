"""Tests for IFCBImageIdParser — new and old IFCB ID formats."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from improv.ids import make_partition_keys
from improv.plugins.ifcb_id import IFCBImageIdParser


@pytest.fixture
def parser():
    return IFCBImageIdParser()


# ---- New format: D{YYYYMMDDTHHMMSS}_IFCB{NNN}[_{ROI}] ----


def test_new_format_image_id(parser):
    parts = parser.parse("D20240101T120000_IFCB107_00001")
    assert parts is not None
    assert parts.instrument == "IFCB107"
    assert parts.timestamp == datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_new_format_sample_id(parser):
    parts = parser.parse("D20240101T120000_IFCB107")
    assert parts is not None
    assert parts.instrument == "IFCB107"
    assert parts.timestamp == datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_new_format_different_instrument(parser):
    parts = parser.parse("D20230615T083045_IFCB14_00099")
    assert parts is not None
    assert parts.instrument == "IFCB14"
    assert parts.timestamp == datetime(2023, 6, 15, 8, 30, 45, tzinfo=timezone.utc)


# ---- Old format: IFCB{N}_{YYYY}_{DDD}_{HHMMSS}[_{ROI}] ----


def test_old_format_image_id(parser):
    # Day 32 = Feb 1
    parts = parser.parse("IFCB1_2014_032_093500_00001")
    assert parts is not None
    assert parts.instrument == "IFCB1"
    assert parts.timestamp == datetime(2014, 2, 1, 9, 35, 0, tzinfo=timezone.utc)


def test_old_format_sample_id(parser):
    parts = parser.parse("IFCB1_2014_032_093500")
    assert parts is not None
    assert parts.instrument == "IFCB1"
    assert parts.timestamp == datetime(2014, 2, 1, 9, 35, 0, tzinfo=timezone.utc)


def test_old_format_day_001(parser):
    parts = parser.parse("IFCB5_2010_001_000000_00001")
    assert parts is not None
    assert parts.instrument == "IFCB5"
    assert parts.timestamp == datetime(2010, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def test_old_format_day_365(parser):
    parts = parser.parse("IFCB5_2014_365_235959")
    assert parts is not None
    assert parts.instrument == "IFCB5"
    assert parts.timestamp == datetime(2014, 12, 31, 23, 59, 59, tzinfo=timezone.utc)


def test_old_format_leap_year(parser):
    # 2016 is a leap year, day 366 = Dec 31
    parts = parser.parse("IFCB5_2016_366_120000")
    assert parts is not None
    assert parts.timestamp == datetime(2016, 12, 31, 12, 0, 0, tzinfo=timezone.utc)


# ---- No match ----


def test_no_match_garbage(parser):
    assert parser.parse("not-an-id") is None


def test_no_match_other_instrument(parser):
    assert parser.parse("ALPHA_20240101T120000_001") is None


def test_no_match_partial(parser):
    assert parser.parse("D20240101T120000") is None


# ---- Integration with make_partition_keys ----


def test_partition_keys_new_format(parser):
    keys = make_partition_keys("D20240315T120000_IFCB107_00001", [parser])
    assert keys == {"instrument": "IFCB107", "year": 2024, "month": 3}


def test_partition_keys_old_format(parser):
    # Day 32 = Feb 1
    keys = make_partition_keys("IFCB1_2014_032_093500_00001", [parser])
    assert keys == {"instrument": "IFCB1", "year": 2014, "month": 2}
