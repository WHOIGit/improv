"""Timestamp validation and clock correction for instrument data.

Timestamps are load-bearing in improv — they are the primary partitioning
axis and the organizing dimension for dataset membership. They must be
validated and bolted down before any write to the columnar store.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol


class ClockCorrection(Protocol):
    """Protocol for instrument-specific clock correction logic."""

    def apply(self, ts: datetime, instrument: str) -> datetime:
        """Return the corrected timestamp for the given instrument."""
        ...


def _as_utc(ts: datetime) -> datetime:
    """Return ts as UTC-aware; assumes UTC if naive."""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def validate_timestamp(
    ts: datetime,
    instrument: str,
    deployment_start: datetime,
    deployment_end: datetime | None = None,
    corrections: list[ClockCorrection] | None = None,
) -> datetime:
    """Validate and optionally correct an instrument timestamp.

    Applies clock corrections first, then checks plausibility:
    - Not in the future
    - Not before deployment_start
    - Not after deployment_end (if set)

    Returns the corrected, validated timestamp.
    Raises ValueError on plausibility failure.
    """
    ts = _as_utc(ts)
    deployment_start = _as_utc(deployment_start)

    if corrections:
        for correction in corrections:
            ts = correction.apply(ts, instrument)

    now = datetime.now(timezone.utc)
    if ts > now:
        raise ValueError(
            f"Timestamp {ts.isoformat()} for instrument {instrument!r} is in the future."
        )
    if ts < deployment_start:
        raise ValueError(
            f"Timestamp {ts.isoformat()} for instrument {instrument!r} is before "
            f"deployment start {deployment_start.isoformat()}."
        )
    if deployment_end is not None:
        deployment_end = _as_utc(deployment_end)
        if ts > deployment_end:
            raise ValueError(
                f"Timestamp {ts.isoformat()} for instrument {instrument!r} is after "
                f"deployment end {deployment_end.isoformat()}."
            )

    return ts
