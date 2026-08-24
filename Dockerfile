# improv REST service.
#
# Two stages: a builder that resolves the locked dependency set, and a slim
# runtime that carries only the resulting virtualenv. The dependency install is
# a separate layer from the project install so that editing src/ does not
# re-resolve ~1 GB of wheels.

ARG PYTHON_VERSION=3.13

# ---------------------------------------------------------------- builder ----
FROM python:${PYTHON_VERSION}-slim AS builder

# git is required, not optional: amplify-db-utils and amplify-storage-utils are
# declared as git URLs in pyproject.toml, so the resolver clones them.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pinned so an image rebuild cannot pick up a uv that resolves differently.
# uv.lock is revision 3; keep this in step with the uv used to write the lock.
ARG UV_VERSION=0.9.15
RUN pip install --no-cache-dir "uv==${UV_VERSION}"

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_CACHE=1

WORKDIR /app

# Dependency layer. --no-install-project means this is invalidated only by a
# pyproject.toml or uv.lock change, not by application code.
#
# --locked is the whole point of copying the lock: amplify-db-utils is declared
# unpinned in pyproject.toml but pinned to a commit in uv.lock, so an unlocked
# install would float it and images would not be reproducible.
#
# --locked, not --frozen: --frozen uses the lock without checking it against
# pyproject.toml, so adding a dependency and forgetting to re-lock builds a wrong
# image silently. That already happened once — the lock predated the
# amplify-storage-utils[s3] extra, and the image came out with no boto3, so the
# S3 object store would have failed at runtime. --locked fails the build instead.
# Re-lock with `uv lock` after any pyproject.toml dependency change.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-editable \
        --extra service --extra vastdb

# Project layer.
COPY src ./src
RUN uv sync --locked --no-dev --no-editable \
        --extra service --extra vastdb

# ---------------------------------------------------------------- runtime ----
FROM python:${PYTHON_VERSION}-slim AS runtime

# ca-certificates for TLS to VAST. psycopg2-binary bundles its own libpq, so
# there is no libpq-dev or compiler in this stage.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Match these to whatever owns a bind-mounted IMPROV_STORAGE_PATH, or the
# container will not be able to write image bytes to it.
ARG UID=1000
ARG GID=1000
RUN groupadd --gid "${GID}" improv \
    && useradd --uid "${UID}" --gid "${GID}" --create-home --shell /usr/sbin/nologin improv

# HOME must be stable and writable: vastdb_store imports duckdb for client-side
# joins, and duckdb writes its extension directory under HOME.
ENV HOME=/home/improv \
    PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder --chown=${UID}:${GID} /app/.venv /app/.venv

WORKDIR /app
USER improv

EXPOSE 8000

# Shallow by design — /healthz touches neither Postgres nor the columnar store,
# so a transient VAST blip does not get a healthy container killed.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"]

# Worker count and the trusted-proxy allowlist are deployment properties, so they
# come from the environment rather than the command line: uvicorn reads
# WEB_CONCURRENCY for --workers and FORWARDED_ALLOW_IPS for --forwarded-allow-ips.
# proxy_headers is already on by default. That keeps the command identical
# everywhere and means compose needs no override.
#
# FORWARDED_ALLOW_IPS is deliberately not defaulted here — uvicorn's own default
# is 127.0.0.1, which is correctly restrictive. Setting it wrong would let any
# client spoof X-Forwarded-For.
ENV WEB_CONCURRENCY=4

CMD ["uvicorn", "improv.asgi:app", "--host", "0.0.0.0", "--port", "8000"]
