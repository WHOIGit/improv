# improv — image provenance

**improv** is a shared data platform for scientific imaging instruments. It provides a single place to store, organize, and query images and their associated scientific products — regardless of instrument type or scale.

Every image in the system accumulates an append-only **provenance log**: geolocation, segmentation outputs, classifier scores, human annotations, oceanographic context. Records are never deleted or overwritten. A classifier can be re-run years later and its outputs attach to the same images alongside the original run.

---

## Overview

### What it stores

| Layer | What | Backend |
|-------|------|---------|
| Image bytes | Raw image data, keyed by image ID | Object store (HashdirStore / S3) |
| Image metadata | One row per image: ID, instrument, timestamp, segmentation lineage | Columnar (DuckDB+Parquet or VAST DB) |
| Provenance | Append-only log of every operation performed on each image | Columnar |
| Plugin indexes | Promoted fields for fast queries (spatial, features, classifications) | Columnar |
| Instruments, samples, datasets | Mutable organizing metadata | PostgreSQL or SQLite |

### What you can query

- **By time and instrument** — the general-purpose access pattern for any instrument
- **By location** — bounding box (lat/lon/depth) via a pre-built spatial index
- **By collection** — named datasets defined as time spans; membership derived automatically
- **By sample** — for instruments with discrete sampling events (e.g., IFCB)
- **By provenance kind** — "what images have features from pipeline X?"

### What it is not

improv is a data substrate. It does not perform segmentation, run classifiers, or manage annotation workflows. Those tools write their outputs into the provenance log. Instrument-specific REST APIs, dashboards, and analysis pipelines sit on top of improv and present data in instrument-appropriate ways.

### Scale

The same API and data model work from a single laptop during a field deployment to a multi-instrument production system with billions of images. No cloud dependency — runs on-premises, on embedded devices, or in the cloud.

---

## Getting started

### Install

Download the code or clone the repository. In the code directory:

```bash
# Base install — for batch producers (ingest pipelines, classifiers)
pip install .

# Service install — adds FastAPI, SQLAlchemy, Alembic, CLI
pip install '.[service]'
```

### Set up the database (service mode)

```bash
export IMPROV_DATABASE_URL="postgresql://user:pass@localhost/improv"
export IMPROV_DB_ROOT="/data/improv/columnar"

improv db upgrade
```

For local development, SQLite + local filesystem work fine:

```bash
export IMPROV_DATABASE_URL="sqlite:///improv.db"
export IMPROV_DB_ROOT="./improv-data"
export IMPROV_STORAGE_PATH="./improv-objects"
```

---

## Usage examples

These examples use a fictional instrument called **MarineScope** (a towed underwater camera). Its image IDs follow the format `MS_{YYYYMMDD}T{HHMMSS}_{index:05d}`, e.g. `MS_20240615T143022_00001`.

### 1. Register a parser and instrument

```python
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
from storage.fs import HashdirStore

from improv.oltp.models import Base
from improv.plugins import GeoLocationPlugin, SampleContextPlugin
from improv.service import ImageService
from improv.store.tables import register_service_tables

store = DuckDBParquetStore(DuckDBParquetConfig(root="/data/improv/columnar"))
engine = create_engine("postgresql://user:pass@localhost/improv")
Base.metadata.create_all(engine)
session = sessionmaker(bind=engine)()
storage = HashdirStore("/data/improv/objects")

parsers = [MarineScopeParser()]
plugins = [GeoLocationPlugin(), SampleContextPlugin()]

register_service_tables(store, plugins)

service = ImageService(
    store=store,
    session=session,
    parsers=parsers,
    plugins=plugins,
    storage=storage,
)
```

### 3. Store image bytes and metadata

```python
from datetime import datetime, timezone
from improv.models import ImageRecord

# Store the raw bytes — keyed by image_id
for i in range(1, 101):
    image_id = f"MS_20240615T143022_{i:05d}"
    storage.put(image_id, raw_image_bytes[i])

# Register the metadata
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

# Write features provenance + dual-write to index table (producer's responsibility)
write_provenance(store, feature_envelopes, parsers=[MarineScopeParser()])
store.write("ifcb_features_index", feature_index_records)
```

### 8. REST API

```python
from improv.api.app import create_app
from improv.config import ImprovConfig
from amplify_db_utils import DuckDBParquetConfig
from storage.fs import HashdirStore
import uvicorn

config = ImprovConfig(
    db_config=DuckDBParquetConfig(root="/data/improv/columnar"),
    database_url="postgresql://user:pass@localhost/improv",
    parsers=[MarineScopeParser()],
    plugins=[GeoLocationPlugin(), SampleContextPlugin()],
    storage=HashdirStore("/data/improv/objects"),
)

app = create_app(config)
uvicorn.run(app, host="0.0.0.0", port=8000)
```

Key endpoints:

```
GET  /images/{image_id}                → image bytes
GET  /images/{image_id}/metadata       → image record JSON
GET  /images/{image_id}/blob           → blob (segmentation mask) bytes
GET  /images/{image_id}/provenance     → full provenance log
GET  /images/{image_id}/provenance/{kind}
GET  /images/search?instrument=...&time_start=...&time_end=...
GET  /images/search?collection=NES-LTER-cruise-EN688
POST /images/ingest                    → register image records
POST /images/{image_id}/provenance     → single provenance (triggers plugin dual-write)
POST /images/provenance/batch          → batch provenance ingest
GET  /instruments/{name}
POST /instruments
GET  /samples/{sample_id}
GET  /samples/{sample_id}/images
POST /samples
POST /samples/batch
GET  /datasets
GET  /datasets/{name}
POST /datasets
POST /datasets/{name}/spans
```

---

## Plugin architecture

Plugins extend the provenance system. Each plugin handles a specific provenance `kind` and optionally maintains an index table for fast querying. The service dispatches provenance records to the matching plugin based on `kind`.

### Built-in plugins

| Plugin | Kind | Index table | Purpose |
|--------|------|-------------|---------|
| `GeoLocationPlugin` | `geolocation` | `geolocation_index` | Spatial queries |
| `SampleContextPlugin` | `sample_context` | `sample_index` | Image↔sample lookups |
| `BlobPlugin` | `blob` | *(none)* | Binary products; storage key in provenance payload |

### Instrument-specific plugins

| Plugin | Kind | Index table | Purpose |
|--------|------|-------------|---------|
| `IFCBFeaturesPlugin` | `ifcb_features` | `ifcb_features_index` | Wide table of morphometric scalars |
| `IFCBCNNClassificationPlugin` | `ifcb_cnn_classification` | `ifcb_cnn_classification_index` | Wide table of class scores |

Instrument-specific plugins live alongside generic ones. The `kind` field determines dispatch. Instrument-facing APIs (e.g., `ifcb-rest-api`) know which kinds to query; improv itself is instrument-agnostic.

---

## Package layout

```
src/improv/
├── models/          # ImageRecord, ProvenanceEnvelope
├── plugins/         # ProvenancePlugin protocol; built-in + instrument-specific plugins
│   ├── geolocation.py
│   ├── sample_context.py
│   ├── blob.py
│   ├── ifcb_features.py
│   └── annotation.py       # MachineAnnotationRecord + IFCBCNNClassificationPlugin
├── ids.py           # ImageIdParser protocol; make_partition_keys()
├── timestamp.py     # validate_timestamp(); ClockCorrection protocol
├── store/           # Columnar store operations (images, provenance, indexes)
├── oltp/            # SQLAlchemy models; Alembic migrations; CRUD queries
├── service.py       # ImageService — central business logic
├── config.py        # ImprovConfig; load_config()
├── api/             # FastAPI app and routers  [service extra]
│   ├── routers/     # images, provenance, blobs, instruments, samples, datasets
│   └── schemas.py   # Pydantic request/response models
└── cli.py           # improv db upgrade        [service extra]
```

## Dependencies

| Package | Install | Role |
|---------|---------|------|
| `amplify-db-utils` | base | Columnar storage (DuckDB+Parquet / VAST DB) |
| `amplify-storage-utils` | base | Object storage (HashdirStore / S3) |
| `pydantic >= 2.0` | base | Models and validation |
| `pyarrow` | base | Columnar data exchange |
| `fastapi` + `uvicorn` | `[service]` | REST API |
| `sqlalchemy` + `alembic` | `[service]` | OLTP store and migrations |
| `click` | `[service]` | CLI (`improv db upgrade`) |
