# improv — image provenance

**improv** is a shared data platform for scientific imaging instruments. It provides a single place to store, organize, and query images and their associated scientific products — regardless of instrument type or scale.

Every image in the system accumulates an append-only **provenance log**: geolocation, segmentation outputs, classifier scores, human annotations, oceanographic context. Records are never deleted or overwritten. A classifier can be re-run years later and its outputs attach to the same images alongside the original run.

---

## Overview

### What it stores

| Layer | What | Backend |
|-------|------|---------|
| Images | One row per image: ID, instrument, timestamp, segmentation lineage | columnar (DuckDB+Parquet or VAST DB) |
| Provenance | Append-only log of every operation performed on each image | columnar |
| Spatial index | Pre-promoted lat/lon for fast bounding-box queries | columnar |
| Sample index | Image↔sample mappings for discrete-sample instruments | columnar |
| Instruments, samples, datasets | Mutable organizing metadata | PostgreSQL |

### What you can query

- **By time and instrument** — the general-purpose access pattern for any instrument
- **By location** — bounding box (lat/lon/depth) via a pre-built spatial index
- **By collection** — named datasets defined as time spans; membership derived automatically
- **By sample** — for instruments with discrete sampling events (e.g., IFCB)
- **By provenance kind** — "what images have features from pipeline X?"

### What it is not

improv is a data substrate. It does not perform segmentation, run classifiers, or manage annotation workflows. Those tools write their outputs into the provenance log. Dashboards, REST APIs, and analysis pipelines read from it.

### Scale

The same API and data model work from a single laptop during a field deployment to a multi-instrument production system with billions of images. No cloud dependency — runs on-premises, on embedded devices, or in the cloud.

---

## Getting started

### Install

```bash
# Base install — for batch producers (ingest pipelines, classifiers)
pip install improv

# Service install — adds FastAPI, SQLAlchemy, Alembic, CLI
pip install 'improv[service]'
```

### Set up the database (service mode)

```bash
export IMPROV_DATABASE_URL="postgresql://user:pass@localhost/improv"
export IMPROV_DB_ROOT="/data/improv/columnar"

improv db upgrade
```

For development, SQLite works fine:

```bash
export IMPROV_DATABASE_URL="sqlite:///improv.db"
```

---

## Usage examples

These examples use a fictional instrument called **MarineScope** (a towed underwater camera). Its image IDs follow the format `MS_{YYYYMMDD}T{HHMMSS}_{index:05d}`, e.g. `MS_20240615T143022_00001`.

### 1. Register a parser and instrument

```python
from dataclasses import dataclass
from datetime import datetime, timezone
from improv.ids import ImageIdParser, ImageIdParts

class MarineScopeParser:
    """Parses IDs like MS_20240615T143022_00001."""

    def parse(self, image_id: str) -> ImageIdParts | None:
        parts = image_id.split("_")
        if len(parts) != 3 or parts[0] != "MS":
            return None
        try:
            ts = datetime.strptime(parts[1], "%Y%m%dT%H%M%S").replace(
                tzinfo=timezone.utc
            )
            return ImageIdParts(instrument="MarineScope-01", timestamp=ts)
        except ValueError:
            return None
```

### 2. Set up the store and service

```python
from amplify_db_utils import DuckDBParquetConfig, DuckDBParquetStore
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from improv.config import ImprovConfig
from improv.oltp.models import Base
from improv.plugins.geolocation import GeoLocationPlugin
from improv.plugins.sample_context import SampleContextPlugin
from improv.service import ImageService
from improv.store.tables import register_service_tables

store = DuckDBParquetStore(DuckDBParquetConfig(root="/data/improv/columnar"))
engine = create_engine("postgresql://user:pass@localhost/improv")
Base.metadata.create_all(engine)
session = sessionmaker(bind=engine)()

parsers = [MarineScopeParser()]
plugins = [GeoLocationPlugin(), SampleContextPlugin()]

register_service_tables(store, plugins)

service = ImageService(
    store=store,
    session=session,
    parsers=parsers,
    plugins=plugins,
)
```

### 3. Ingest images

```python
from datetime import datetime, timezone
from improv.models import ImageRecord

images = [
    ImageRecord(
        image_id=f"MS_20240615T143022_{i:05d}",
        timestamp=datetime(2024, 6, 15, 14, 30, 22, tzinfo=timezone.utc),
        instrument="MarineScope-01",
    )
    for i in range(1, 101)
]

service.ingest_images(images)
```

### 4. Attach provenance — geolocation

```python
from improv.models import ProvenanceEnvelope

geo_records = [
    ProvenanceEnvelope(
        image_id=f"MS_20240615T143022_{i:05d}",
        kind="geolocation",
        source="nav_track_interpolation_v2",
        timestamp=datetime(2024, 6, 15, 14, 30, 22, tzinfo=timezone.utc),
        data={
            "lat": 41.32 + i * 0.0001,
            "lon": -70.55,
            "depth": 12.5,
            "source": "nav_track_interpolation_v2",
            "version": "2.1",
            "computed_at": "2024-06-16T08:00:00Z",
        },
        instrument="MarineScope-01",
    )
    for i in range(1, 101)
]

service.ingest_provenance(geo_records)
```

Geolocation records are dual-written to a spatial index automatically. No separate indexing step needed.

### 5. Query images

```python
from datetime import datetime, timezone

# All images from a time window
images = service.query_images(
    instrument="MarineScope-01",
    time_start=datetime(2024, 6, 15, 14, 0, tzinfo=timezone.utc),
    time_end=datetime(2024, 6, 15, 15, 0, tzinfo=timezone.utc),
)

# Spatiotemporal bounding box
images = service.query_images(
    instrument="MarineScope-01",
    time_start=datetime(2024, 6, 15, 14, 0, tzinfo=timezone.utc),
    time_end=datetime(2024, 6, 15, 15, 0, tzinfo=timezone.utc),
    lat_min=41.30, lat_max=41.40,
    lon_min=-70.60, lon_max=-70.50,
)

# All images in a named dataset
images = list(service.get_dataset_images("NES-LTER-cruise-EN688"))
```

### 6. Retrieve provenance

```python
# Full provenance log for one image
records = service.get_provenance("MS_20240615T143022_00001")

# Just the geolocation records
geo = service.get_provenance("MS_20240615T143022_00001", kind="geolocation")
print(geo[0].data)
# {'lat': 41.3201, 'lon': -70.55, 'depth': 12.5, ...}
```

### 7. Batch producer (no HTTP)

Batch pipelines (feature extraction, classifiers) import directly — no REST layer involved:

```python
from improv.models import ImageRecord, ProvenanceEnvelope
from improv.store.images import write_images
from improv.store.provenance import write_provenance
from improv.store.tables import register_service_tables

# At pipeline startup (idempotent)
register_service_tables(store, plugins=[])

# Write a batch of images
write_images(store, image_records, parsers=[MarineScopeParser()])

# Write features provenance + dual-write to features_index (producer's responsibility)
write_provenance(store, feature_envelopes, parsers=[MarineScopeParser()])
store.write("features_index", feature_index_records)
```

### 8. REST API

```python
from improv.api.app import create_app
from improv.config import ImprovConfig
from amplify_db_utils import DuckDBParquetConfig
import uvicorn

config = ImprovConfig(
    db_config=DuckDBParquetConfig(root="/data/improv/columnar"),
    database_url="postgresql://user:pass@localhost/improv",
    parsers=[MarineScopeParser()],
    plugins=[GeoLocationPlugin(), SampleContextPlugin()],
)

app = create_app(config)
uvicorn.run(app, host="0.0.0.0", port=8000)
```

Key endpoints:

```
GET  /images/{image_id}
GET  /images?instrument=MarineScope-01&time_start=2024-06-15T14:00:00Z&time_end=...
GET  /images?collection=NES-LTER-cruise-EN688
GET  /images/{image_id}/provenance
GET  /images/{image_id}/provenance/geolocation
POST /images                           (ingest)
POST /images/{image_id}/provenance     (single; triggers plugin dual-write)
POST /images/provenance/batch          (small batch)
GET  /samples/{sample_id}
GET  /samples/{sample_id}/images
GET  /images/{image_id}/blob
```

---

## Package layout

```
src/improv/
├── models/          # ImageRecord, ProvenanceEnvelope
├── plugins/         # ProvenancePlugin protocol; built-in geolocation + sample_context
├── ids.py           # ImageIdParser protocol; make_partition_keys()
├── timestamp.py     # validate_timestamp(); ClockCorrection protocol
├── store/           # columnar store operations (images, provenance, indexes)
├── oltp/            # SQLAlchemy models; Alembic migrations; CRUD queries
├── service.py       # ImageService — central business logic
├── config.py        # ImprovConfig; load_config()
├── api/             # FastAPI app and routers  [service extra]
└── cli.py           # improv db upgrade        [service extra]
```

## Dependencies

| Package | Install | Role |
|---------|---------|------|
| `amplify-db-utils` | base | Columnar storage (DuckDB+Parquet / VAST DB) |
| `amplify-storage-utils` | base | Binary product retrieval via object store |
| `pydantic >= 2.0` | base | Models and validation |
| `pyarrow` | base | Columnar data exchange |
| `fastapi` + `uvicorn` | `[service]` | REST API |
| `sqlalchemy` + `alembic` | `[service]` | OLTP store and migrations |
| `click` | `[service]` | CLI (`improv db upgrade`) |
