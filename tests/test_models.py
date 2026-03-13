"""Tests for core Pydantic models."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from improv.models.image import ImageRecord
from improv.models.provenance import ProvenanceEnvelope


def test_image_record_minimal():
    r = ImageRecord(
        image_id="ALPHA_20240115T120000_001",
        timestamp=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
    )
    assert r.image_id == "ALPHA_20240115T120000_001"
    assert r.instrument is None
    assert r.roi_index is None


def test_image_record_full():
    r = ImageRecord(
        image_id="ALPHA_20240115T120000_001",
        timestamp=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
        instrument="ALPHA",
        year=2024,
        month=1,
        parent_image_id="FRAME_001",
        segmentation_run_id="yolov8-r1",
        roi_index=42,
        bbox_x=10,
        bbox_y=20,
        bbox_w=50,
        bbox_h=60,
    )
    assert r.roi_index == 42
    assert r.bbox_w == 50


def test_image_record_json_roundtrip():
    r = ImageRecord(
        image_id="ALPHA_20240115T120000_001",
        timestamp=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
        instrument="ALPHA",
    )
    json_str = r.model_dump_json()
    r2 = ImageRecord.model_validate_json(json_str)
    assert r2 == r


def test_image_record_requires_image_id():
    with pytest.raises(ValidationError):
        ImageRecord(timestamp=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc))


def test_provenance_envelope_minimal():
    env = ProvenanceEnvelope(
        image_id="ALPHA_20240115T120000_001",
        kind="geolocation",
        source="nav_track_v1",
        timestamp=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
        data={"lat": 41.5, "lon": -70.5},
    )
    assert env.kind == "geolocation"
    assert env.data["lat"] == 41.5


def test_provenance_envelope_json_roundtrip():
    env = ProvenanceEnvelope(
        image_id="img1",
        kind="features",
        source="ifcb-features-v2",
        timestamp=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
        data={"area": 123.4, "perimeter": 45.6},
        instrument="ALPHA",
        year=2024,
        month=1,
    )
    json_str = env.model_dump_json()
    env2 = ProvenanceEnvelope.model_validate_json(json_str)
    assert env2 == env
