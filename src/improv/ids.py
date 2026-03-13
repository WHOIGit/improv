"""Image ID parsing and partition key extraction.

Each instrument registers an ImageIdParser at startup. Parsers are tried in
order; each returns None if the ID doesn't match its pattern. Callers pass
an instrument hint for point lookups when no parser matches.

Write path is never ambiguous — ImageRecord always carries explicit instrument
and timestamp, so partition keys are fully determined at write time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class ImageIdParts:
    """Instrument identity and acquisition timestamp extracted from an image ID."""
    instrument: str
    timestamp: datetime


class ImageIdParser(Protocol):
    """Protocol for instrument-specific image ID parsers.

    Parsers must be mutually exclusive — if multiple parsers could match the
    same ID format, behaviour is undefined (first match wins).
    """

    def parse(self, image_id: str) -> ImageIdParts | None:
        """Parse image_id and return ImageIdParts, or None if it doesn't match."""
        ...


def make_partition_keys(
    image_id: str,
    parsers: list[ImageIdParser],
    instrument_hint: str | None = None,
) -> dict:
    """Extract partition key fields from an image ID.

    Tries each parser in order. On a match, returns
    ``{"instrument": ..., "year": ..., "month": ...}`` derived from the
    parser's extracted timestamp.

    Falls back to ``instrument_hint`` when no parser matches, returning
    ``{"instrument": ...}`` only (year/month not available from hint alone;
    callers should derive them from the record's own timestamp).

    Raises ValueError if neither a parser match nor a hint is available.
    """
    for parser in parsers:
        parts = parser.parse(image_id)
        if parts is not None:
            return {
                "instrument": parts.instrument,
                "year": parts.timestamp.year,
                "month": parts.timestamp.month,
            }

    if instrument_hint is not None:
        return {"instrument": instrument_hint}

    raise ValueError(
        f"Cannot determine instrument for image_id {image_id!r}: "
        "no parser matched and no instrument hint provided."
    )
