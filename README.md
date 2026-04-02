# improv — image provenance

**improv** is a shared data platform for scientific imaging instruments. It stores, organizes, and queries images and their associated scientific products — regardless of instrument type or scale.

Every image accumulates an append-only **provenance log**: geolocation, segmentation outputs, classifier scores, human annotations, oceanographic context. Records are never deleted or overwritten. A classifier can be re-run years later and its outputs attach to the same images alongside the original run.

## Architecture

improv has three storage layers:

- **Object store** — raw image bytes and binary products (segmentation masks, etc.), keyed by image ID
- **Columnar store** — queryable image metadata, provenance records, and plugin index tables (DuckDB+Parquet or VAST DB)
- **OLTP database** — mutable organizing metadata: instruments, samples, datasets, ingest tasks (PostgreSQL or SQLite)

A **plugin system** extends provenance handling. Each plugin handles a specific provenance `kind` and optionally maintains an index table for fast querying. Plugins can be generic (geolocation, sample context) or instrument-specific (IFCB morphometric features, IFCB CNN classification scores).

## Access patterns

- By time and instrument
- By spatial bounding box (lat/lon/depth)
- By named dataset (defined as time spans)
- By sample (for discrete-sample instruments)
- By provenance kind

## REST API

improv exposes a FastAPI service with endpoints for image data and metadata, provenance, instruments, samples, datasets, and ingest task tracking. A thin HTTP client (`improv.client.ImprovClient`) is provided for ingest scripts that need OLTP access without direct database credentials.

## Ingest architecture

Batch producers (ingest pipelines, classifiers) use a hybrid approach:

- **OLTP operations** (register instruments, samples, ingest tasks) go through the REST API
- **High-volume writes** (image metadata, provenance, index tables, image bytes) go directly to the columnar store and object store

This avoids coupling ingest scripts to the database while keeping high-throughput writes off the HTTP path.

## Install

```bash
pip install .            # base — columnar store, object store, models, client
pip install '.[db]'      # adds SQLAlchemy for direct OLTP access
pip install '.[service]' # adds FastAPI, CLI, migrations
```

## Dependencies

| Package | Role |
|---------|------|
| `amplify-db-utils` | Columnar storage (DuckDB+Parquet / VAST DB) |
| `amplify-storage-utils` | Object storage (HashdirStore / S3) |
| `pydantic` | Models and validation |
| `pyarrow` | Columnar data exchange |
| `httpx` | Thin ingest client |
| `fastapi`, `sqlalchemy`, `alembic` | Service extras |
