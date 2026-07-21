"""Canonical hashing of provenance payloads.

Idempotency for the append-only provenance log rests on a content hash: a
retried write re-appends a byte-identical row that is collapsed at read time,
while a genuinely different payload hashes differently and is retained.

The hash is computed over the RFC 8785 JSON Canonicalization Scheme (JCS) form
of the payload, so two semantically-equal payloads hash identically regardless
of key order, whitespace, or numeric formatting (e.g. ``1.0`` and ``1`` both
canonicalize to ``1``). This holds across producers in different languages
(Python, MATLAB, JS), which flat ``json.dumps(sort_keys=True)`` does not
guarantee. NaN/Infinity are rejected — they are not valid JSON.
"""

from __future__ import annotations

import hashlib

import rfc8785


def canonical_data_hash(data: dict) -> str:
    """Return the SHA-256 hex digest of *data*'s RFC 8785 canonical form.

    Raises ``ValueError`` (via rfc8785) if *data* contains NaN/Infinity or a
    value with no canonical JSON representation.
    """
    return hashlib.sha256(rfc8785.dumps(data)).hexdigest()
