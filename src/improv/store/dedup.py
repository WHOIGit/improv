"""Read-time deduplication for the append-only columnar store.

Writes are append-only across every backend, so a retried write re-appends
rows. Dedup at read restores idempotency: byte-identical rows collapse to one,
while genuinely different rows are retained.

Index rows are deterministic projections of provenance with no write-time-varying
column, so an exact retry produces a byte-identical row and full-row equality is
a sound identity. (Provenance rows carry a write-time ``written_at`` and an
opaque JSON ``data`` blob, so they dedup on an explicit identity key instead —
see ``store.provenance``.)
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Sequence


def dedup_rows(
    rows: Iterable[dict],
    exclude: Sequence[str] = (),
) -> list[dict]:
    """Collapse rows identical across all columns (minus ``exclude``).

    Order-preserving; the first occurrence of each identity wins. All retained
    column values must be hashable (scalar columns are — index rows have no
    nested values).
    """
    exclude_set = set(exclude)
    seen: set[tuple] = set()
    out: list[dict] = []
    for row in rows:
        # Keys are unique per row, so sorting by key never compares values —
        # values need only be hashable, not orderable.
        key = tuple(sorted((k, v) for k, v in row.items() if k not in exclude_set))
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out
