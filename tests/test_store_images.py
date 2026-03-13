"""Tests for store/images.py."""

from __future__ import annotations

from datetime import datetime, timezone

from improv.models.image import ImageRecord
from improv.store.images import (
    bulk_get_images,
    get_image,
    get_images,
    write_images,
)


def make_record(suffix: str, ts: datetime, instrument: str = "ALPHA") -> ImageRecord:
    image_id = f"ALPHA_{ts.strftime('%Y%m%dT%H%M%S')}_{suffix}"
    return ImageRecord(image_id=image_id, timestamp=ts, instrument=instrument)


def test_write_and_read_round_trip(store_with_tables, parsers, ts_jan):
    record = make_record("001", ts_jan)
    write_images(store_with_tables, [record], parsers)

    result = get_image(store_with_tables, record.image_id, parsers)
    assert result is not None
    assert result.image_id == record.image_id


def test_partition_keys_populated(store_with_tables, parsers, ts_jan):
    record = make_record("001", ts_jan)
    write_images(store_with_tables, [record], parsers)

    result = get_image(store_with_tables, record.image_id, parsers)
    assert result.instrument == "ALPHA"
    assert result.year == 2024
    assert result.month == 1


def test_hint_fallback_read(store_with_tables, parsers, ts_jan):
    """get_image with hint falls back to scanning the instrument partition."""
    record = ImageRecord(
        image_id="UNKNOWN_IMG_001",
        timestamp=ts_jan,
        instrument="ALPHA",
    )
    write_images(store_with_tables, [record], parsers)

    result = get_image(
        store_with_tables, "UNKNOWN_IMG_001", parsers, instrument_hint="ALPHA"
    )
    assert result is not None
    assert result.image_id == "UNKNOWN_IMG_001"


def test_get_image_not_found(store_with_tables, parsers):
    result = get_image(
        store_with_tables, "ALPHA_20240115T120000_999", parsers
    )
    assert result is None


def test_range_query(store_with_tables, parsers, ts_jan, ts_feb):
    r1 = make_record("001", ts_jan)
    r2 = make_record("002", ts_feb)
    write_images(store_with_tables, [r1, r2], parsers)

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 31, tzinfo=timezone.utc)
    results = list(get_images(store_with_tables, "ALPHA", start, end))
    ids = [r.image_id for r in results]
    assert r1.image_id in ids
    assert r2.image_id not in ids


def test_bulk_get_returns_arrow_table(store_with_tables, parsers, ts_jan, ts_feb):
    import pyarrow as pa
    r1 = make_record("001", ts_jan)
    r2 = make_record("002", ts_feb)
    write_images(store_with_tables, [r1, r2], parsers)

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 12, 31, tzinfo=timezone.utc)
    table = bulk_get_images(store_with_tables, "ALPHA", start, end)
    assert isinstance(table, pa.Table)
    assert table.num_rows == 2


def test_segmentation_fields_preserved(store_with_tables, parsers, ts_jan):
    record = ImageRecord(
        image_id="ALPHA_20240115T120000_001",
        timestamp=ts_jan,
        instrument="ALPHA",
        roi_index=5,
        bbox_x=10,
        bbox_y=20,
        bbox_w=30,
        bbox_h=40,
    )
    write_images(store_with_tables, [record], parsers)
    result = get_image(store_with_tables, record.image_id, parsers)
    assert result.roi_index == 5
    assert result.bbox_x == 10
