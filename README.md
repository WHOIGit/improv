# improv — image provenance

**improv** is a shared data platform for scientific imaging instruments. It stores, organizes, and queries images and their associated scientific products — regardless of instrument type or scale.

Every image accumulates an append-only **provenance log**: geolocation, segmentation outputs, classifier scores, human annotations, oceanographic context. Records are never deleted or overwritten. A classifier can be re-run years later and its outputs attach to the same images alongside the original run.

## Architecture

improv has three storage layers:

- **Object store** — raw image bytes and binary products (segmentation masks, etc.), keyed by image ID
- **Columnar store** — queryable image metadata, provenance records, and plugin index tables (DuckDB+Parquet or VAST DB)
- **OLTP database** — mutable organizing metadata: instruments, samples, datasets, ingest tasks (PostgreSQL or SQLite)

A **plugin system** extends provenance handling. Plugins register via dependency injection — the core never imports them at load time. Each plugin handles a specific provenance `kind` and optionally maintains an index table for fast querying. Plugins are generic and parameterized (geolocation, sample context, machine classification); instrument-specific presets live under `improv.plugins.ifcb` (IFCB morphometric features, IFCB CNN classification), pinning a `kind`/`index_table` onto a generic plugin.

## Access patterns

- By time and instrument
- By spatial bounding box (lat/lon/depth)
- By named dataset (defined as time spans)
- By sample (for discrete-sample instruments)
- By provenance kind

## REST API

improv exposes a FastAPI service with endpoints for image data and metadata, provenance, instruments, samples, datasets, and ingest task tracking. Classifier support adds taxonomy registration/lookup and two decode paths: a stateless decode (caller supplies a vector) and a decoded read that fetches an image's classification provenance and resolves each record against its own `model_version`. A thin HTTP client (`improv.client.ImprovClient`) is provided for ingest scripts that need OLTP access without direct database credentials, including taxonomy registration.

## Authentication

The service authenticates with a single shared bearer token, supplied as `IMPROV_API_TOKEN`. It is **required** — `create_app` refuses to start without it rather than silently serving an unprotected API.

```bash
export IMPROV_API_TOKEN='...'   # generate with: python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Callers pass it as `Authorization: Bearer <token>`. Missing or invalid token → `401`; a valid token lacking the required scope → `403`.

Protection is declared per endpoint by scope, not inferred from the HTTP verb:

| Surface | Auth |
|---------|------|
| All writes (image ingest, provenance ingest, instrument/sample/dataset/taxonomy registration, ingest-task create/update/delete) | `write` scope |
| Ingest-task read, classifier decode | `read` scope |
| Image bytes, blobs, metadata, image/sample search, provenance reads, dataset and instrument lookup, taxonomy lookup | **open** — no token |

Reads of image and provenance data are deliberately open: the service is deployed inside the on-prem network and the token exists to gate mutation and the ingest-coordination surface, not to keep science data private. Deployments needing read authentication should put the service behind a reverse proxy, or add `require_scope(READ)` to the read routes.

Token handling is swappable. `improv.api.auth` defines a `TokenVerifier` protocol whose only implementation today is `StaticTokenVerifier`; moving to per-client tokens with real per-token scopes means adding a DB-backed verifier and changing the single construction site in `create_app` — routes are untouched.

`ImprovClient` reads `IMPROV_API_TOKEN` from the environment by default, or takes it explicitly:

```python
ImprovClient("http://improv.example:8000", token="...")
```

## Ingest architecture

Batch producers (ingest pipelines, classifiers) use a hybrid approach:

- **OLTP operations** (register instruments, samples, ingest tasks, classifier taxonomies) go through the REST API
- **High-volume writes** (image metadata, provenance, index tables, image bytes) go directly to the columnar store and object store

This avoids coupling ingest scripts to the database while keeping high-throughput writes off the HTTP path. Low-volume producers that prefer not to depend on the columnar store directly can post small provenance batches over REST (`POST /images/provenance/batch`, one instrument per batch).

## Idempotency

The provenance log is append-only, so writes are never overwritten — idempotency is achieved by **appending, then deduplicating at read time**. This works identically on every backend (VAST DB, DuckDB+Parquet, and any future one), because append is the only operation they all share.

- A **provenance record** is identified by `(image_id, kind, source, data_hash)`, where `data_hash` is a canonical [RFC 8785 (JCS)](https://www.rfc-editor.org/rfc/rfc8785) hash of the `data` payload, stamped server-side. Re-posting a byte-identical record re-appends a row that collapses to one on read; a genuinely different payload (e.g. a new `model_version`) hashes differently and is retained. Canonicalization normalizes key order and number formatting (`1.0` == `1`) across producers in different languages, and rejects NaN/Infinity.
- **Index records** are deterministic projections deduplicated on their full column tuple.

**Client contract:** a record's `timestamp` is the **event time** (when the image was collected, or the classifier result produced) — a property of the observed fact, captured once. It is *not* the time of the HTTP request. Retries must resend the identical record, so put real event time in `timestamp`, never wall-clock-at-send; otherwise each attempt looks distinct and will not deduplicate. (The server separately records its own write time.)

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
| `rfc8785` | Canonical (JCS) hashing of provenance payloads for idempotency |
| `httpx` | Thin ingest client |
| `fastapi`, `sqlalchemy`, `alembic` | Service extras |
