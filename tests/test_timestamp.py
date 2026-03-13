"""Tests for timestamp.py — validation and clock correction."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from improv.timestamp import ClockCorrection, validate_timestamp

DEPLOY_START = datetime(2022, 1, 1, tzinfo=timezone.utc)
DEPLOY_END = datetime(2025, 12, 31, tzinfo=timezone.utc)
INSTRUMENT = "TEST_INST"


def valid_ts():
    return datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_valid_timestamp_passes():
    ts = validate_timestamp(valid_ts(), INSTRUMENT, DEPLOY_START, DEPLOY_END)
    assert ts == valid_ts()


def test_future_timestamp_rejected():
    future = datetime.now(timezone.utc) + timedelta(days=1)
    with pytest.raises(ValueError, match="in the future"):
        validate_timestamp(future, INSTRUMENT, DEPLOY_START)


def test_pre_deployment_rejected():
    before = datetime(2021, 12, 31, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="before deployment start"):
        validate_timestamp(before, INSTRUMENT, DEPLOY_START)


def test_post_deployment_rejected():
    after = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="after deployment end"):
        validate_timestamp(after, INSTRUMENT, DEPLOY_START, DEPLOY_END)


def test_no_deployment_end_allows_recent():
    recent = datetime(2025, 1, 1, tzinfo=timezone.utc)
    ts = validate_timestamp(recent, INSTRUMENT, DEPLOY_START)
    assert ts == recent


def test_naive_timestamp_treated_as_utc():
    naive = datetime(2024, 6, 1, 12, 0, 0)  # no tzinfo
    ts = validate_timestamp(naive, INSTRUMENT, DEPLOY_START)
    assert ts.tzinfo == timezone.utc


def test_clock_correction_applied():
    class FixedOffset:
        def apply(self, ts: datetime, instrument: str) -> datetime:
            return ts + timedelta(seconds=30)

    ts_before = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    ts_after = validate_timestamp(
        ts_before, INSTRUMENT, DEPLOY_START, corrections=[FixedOffset()]
    )
    assert ts_after == ts_before + timedelta(seconds=30)


def test_correction_applied_before_plausibility():
    """Correction can push a pre-deployment timestamp into the valid range."""

    class ShiftForward:
        def apply(self, ts: datetime, instrument: str) -> datetime:
            return ts + timedelta(days=365)

    # ts starts before deployment_start
    pre = datetime(2021, 6, 1, tzinfo=timezone.utc)
    ts = validate_timestamp(
        pre,
        INSTRUMENT,
        DEPLOY_START,
        corrections=[ShiftForward()],
    )
    assert ts > DEPLOY_START
