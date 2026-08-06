"""Tests for IFCBImageIdParser — new and old IFCB ID formats."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from improv.ids import make_partition_keys
from improv.plugins.ifcb import IFCBImageIdParser


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


# ---- Shape matches, values out of range ----
#
# The regexes constrain digit count, not range. These IDs reach the datetime
# construction, which must yield None rather than raising — an escaping
# ValueError surfaces as a 500 on the ingest path.


@pytest.mark.parametrize(
    "image_id",
    [
        "D20240115T120097_IFCB107_00061",  # second 97
        "D20240115T129900_IFCB107_00001",  # minute 99
        "D20240115T990000_IFCB107_00001",  # hour 99
        "D20241315T120000_IFCB107_00001",  # month 13
        "D20240132T120000_IFCB107_00001",  # day 32 in January
        "D20230229T120000_IFCB107_00001",  # Feb 29 in a non-leap year
    ],
)
def test_new_format_out_of_range_returns_none(parser, image_id):
    assert parser.parse(image_id) is None


@pytest.mark.parametrize(
    "image_id",
    [
        "IFCB1_2014_123_997700_00001",  # hour 99
        "IFCB1_2014_123_009977_00001",  # second 77
        "IFCB1_2014_000_093500_00001",  # day of year 0
        "IFCB1_2014_999_093500_00001",  # day of year 999 — must not roll years
        "IFCB1_2014_366_093500_00001",  # day 366 in a non-leap year
    ],
)
def test_old_format_out_of_range_returns_none(parser, image_id):
    assert parser.parse(image_id) is None


def test_old_format_doy_does_not_roll_into_a_later_year(parser):
    """doy 999 previously parsed as 2016-09-25 — a plausible but wrong date."""
    assert parser.parse("IFCB1_2014_999_093500_00001") is None


# ---- Integration with make_partition_keys ----


def test_partition_keys_new_format(parser):
    keys = make_partition_keys("D20240315T120000_IFCB107_00001", [parser])
    assert keys == {"instrument": "IFCB107", "year": 2024, "month": 3}


def test_partition_keys_old_format(parser):
    # Day 32 = Feb 1
    keys = make_partition_keys("IFCB1_2014_032_093500_00001", [parser])
    assert keys == {"instrument": "IFCB1", "year": 2014, "month": 2}
