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
pip install '.[service]' # adds FastAPI, CLI, migrations, S3 object store
pip install '.[vastdb]'  # adds the VAST DB columnar backend
```

## Running the service

The service is configured entirely from the environment. `improv.asgi:app`
builds it by calling `load_config()` and `create_app()`.

```bash
# Schema is owned by Alembic — run migrations before serving.
improv db upgrade

uvicorn improv.asgi:app --host 0.0.0.0 --port 8000 --workers 4 \
        --proxy-headers --forwarded-allow-ips=<reverse-proxy-ip>
```

`--proxy-headers` matters whenever a reverse proxy terminates the connection;
without it the client IP and scheme the app sees are the proxy's.

`GET /healthz` is open and shallow — it touches neither Postgres nor the
columnar store, so it reports process liveness rather than dependency health.

### Environment variables

**Columnar store**

| Variable | Notes |
|----------|-------|
| `IMPROV_DB_BACKEND` | `duckdb` (default) or `vastdb` |
| `IMPROV_DB_ROOT` | duckdb: local path or `s3://bucket/prefix` — **required** |
| `IMPROV_S3_ENDPOINT` | duckdb on S3: bare `host:port`, e.g. `vast-s3.whoi.edu:9000` |
| `IMPROV_S3_ACCESS_KEY`, `IMPROV_S3_SECRET_KEY` | duckdb on S3 |
| `IMPROV_S3_USE_SSL` | set `false` for an http-only endpoint |
| `IMPROV_DUCKDB_THREADS` | DuckDB thread count; default is all cores |
| `IMPROV_VASTDB_ENDPOINT` | vastdb — **required** |
| `IMPROV_VASTDB_ACCESS_KEY`, `IMPROV_VASTDB_SECRET_KEY` | vastdb — **required** |
| `IMPROV_VASTDB_BUCKET`, `IMPROV_VASTDB_SCHEMA` | vastdb — **required** |

**OLTP database**

| Variable | Notes |
|----------|-------|
| `IMPROV_DATABASE_URL` | SQLAlchemy URL, e.g. `postgresql+psycopg2://user:pass@host/improv`. **Required** to serve — the service refuses to start without it rather than falling back to a throwaway in-memory database |

**Plugins and parsers**

Comma-separated names, instantiated in order. An unknown name fails startup:
a plugin that is configured but not registered would leave its index table
missing and its provenance kind unindexed, which otherwise only shows up much
later as empty query results.

| Variable | Available values |
|----------|------------------|
| `IMPROV_PLUGINS` | `geolocation`, `sample_context`, `blob`, `machine_classification`, `ifcb_features`, `ifcb_cnn_classification` |
| `IMPROV_PARSERS` | `ifcb` |

**Object store** — at most one; S3 wins if both are configured.

| Variable | Notes |
|----------|-------|
| `IMPROV_OBJECT_BUCKET` | bucket for image bytes and blobs; selects the S3 backend |
| `IMPROV_OBJECT_S3_ENDPOINT` | full URL **with scheme**, e.g. `https://vast-s3.whoi.edu` — note this differs from `IMPROV_S3_ENDPOINT`, which DuckDB and PyArrow want as a bare `host:port` |
| `IMPROV_OBJECT_S3_ACCESS_KEY`, `IMPROV_OBJECT_S3_SECRET_KEY` | |
| `IMPROV_OBJECT_S3_CA_BUNDLE` | CA bundle path for an internally-signed endpoint |
| `IMPROV_STORAGE_PATH` | local/NFS path, selects `HashdirStore` instead |

**Auth**

| Variable | Notes |
|----------|-------|
| `IMPROV_API_TOKEN` | **Required.** See Authentication above |

### Concurrency

Every route handler is synchronous, so FastAPI runs them in a threadpool. The
SQLAlchemy `Session` is therefore created **per request** (see
`improv.api.deps.get_service`) — a `Session` is not thread-safe, and running
more worker processes does not help, since each process would still share one
`Session` across its own threadpool. The columnar store, parsers, plugins and
object store are shared process-wide.

> **The DuckDB+Parquet backend is not safe under concurrent reads.**
> `DuckDBParquetStore` issues every query on one shared DuckDB connection, and
> `read()` is a generator, so concurrent (or merely interleaved) reads clobber
> each other's result set and silently return no rows. Measured at 20 threads:
> ~40–50% of reads returned empty for a record that was present. This is a
> property of `amplify-db-utils`, independent of improv. Until it is fixed
> upstream, treat the DuckDB backend as single-threaded/development-only and use
> VAST DB for any concurrent deployment.

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
