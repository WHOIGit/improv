"""IFCB image ID parser.

Handles two IFCB naming conventions:

**New format** (post-2012 firmware)::

    D20240101T120000_IFCB107_00001
    ├── D{YYYYMMDDTHHMMSS} ── acquisition timestamp
    ├── IFCB{NNN} ─────────── instrument serial number
    └── {NNNNN} ───────────── ROI number (optional — sample-level IDs omit it)

**Old format** (legacy firmware)::

    IFCB1_2014_123_093500_00001
    ├── IFCB{N} ───── instrument serial number
    ├── {YYYY} ────── year
    ├── {DDD} ─────── day of year (1-indexed)
    ├── {HHMMSS} ──── time of day
    └── {NNNNN} ───── ROI number (optional)
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from improv.ids import ImageIdParts

# D20240101T120000_IFCB107           (sample-level)
# D20240101T120000_IFCB107_00001     (image-level)
_NEW_RE = re.compile(
    r"^D(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})_(IFCB\d+)(?:_\d+)?$"
)

# IFCB1_2014_123_093500              (sample-level)
# IFCB1_2014_123_093500_00001        (image-level)
_OLD_RE = re.compile(
    r"^(IFCB\d+)_(\d{4})_(\d{1,3})_(\d{2})(\d{2})(\d{2})(?:_\d+)?$"
)


class IFCBImageIdParser:
    """ImageIdParser implementation for IFCB instruments."""

    def parse(self, image_id: str) -> ImageIdParts | None:
        """Parse an IFCB image or sample ID into instrument + timestamp."""
        m = _NEW_RE.match(image_id)
        if m:
            year, month, day, hour, minute, second, instrument = (
                int(m.group(1)),
                int(m.group(2)),
                int(m.group(3)),
                int(m.group(4)),
                int(m.group(5)),
                int(m.group(6)),
                m.group(7),
            )
            ts = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
            return ImageIdParts(instrument=instrument, timestamp=ts)

        m = _OLD_RE.match(image_id)
        if m:
            instrument = m.group(1)
            year = int(m.group(2))
            doy = int(m.group(3))
            hour, minute, second = int(m.group(4)), int(m.group(5)), int(m.group(6))
            # day-of-year → month/day
            ts = datetime(year, 1, 1, hour, minute, second, tzinfo=timezone.utc) + timedelta(days=doy - 1)
            return ImageIdParts(instrument=instrument, timestamp=ts)

        return None
