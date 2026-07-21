"""Thin HTTP client for improv OLTP operations.

Used by ingest scripts and batch producers that need to register instruments,
samples, etc. via the REST API without depending on SQLAlchemy or direct
database access.

Columnar store and object store writes remain direct — only OLTP operations
go through HTTP.

Scope
-----
This is the ingest-producer surface, not a full mirror of the REST API:
instruments, samples, ingest tasks, and taxonomy registration (plus the one
taxonomy read a producer needs). Read/query and score-decode endpoints are
intentionally omitted.
"""

from __future__ import annotations

from datetime import datetime

import httpx


class ImprovClient:
    """HTTP client for improv OLTP operations.

    Parameters
    ----------
    base_url : str
        The base URL of the improv REST API (e.g. "http://localhost:8000").
    token : str | None
        Optional bearer token for authentication.
    timeout : float
        Request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        timeout: float = 30.0,
        _client: httpx.Client | None = None,
    ) -> None:
        if _client is not None:
            self._client = _client
        else:
            headers = {}
            if token is not None:
                headers["Authorization"] = f"Bearer {token}"
            self._client = httpx.Client(
                base_url=base_url,
                headers=headers,
                timeout=timeout,
            )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ImprovClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Instruments
    # ------------------------------------------------------------------

    def register_instrument(
        self,
        name: str,
        type: str,
        deployment_start: datetime,
        serial_number: str | None = None,
        deployment_end: datetime | None = None,
        description: str | None = None,
    ) -> tuple[dict, bool]:
        """Register an instrument. Returns (instrument_dict, created).

        Returns created=False if the instrument already exists (409).
        """
        resp = self._client.post(
            "/instruments",
            json={
                "name": name,
                "type": type,
                "deployment_start": deployment_start.isoformat(),
                "serial_number": serial_number,
                "deployment_end": deployment_end.isoformat() if deployment_end else None,
                "description": description,
            },
        )
        if resp.status_code == 409:
            return self.get_instrument(name), False
        resp.raise_for_status()
        return resp.json(), True

    def get_instrument(self, name: str) -> dict | None:
        """Get an instrument by name. Returns None if not found."""
        resp = self._client.get(f"/instruments/{name}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Samples
    # ------------------------------------------------------------------

    def register_sample(
        self,
        sample_id: str,
        instrument: str,
        time_start: datetime,
        time_end: datetime,
        quality_flag: int | None = None,
        alternate_sample_id: str | None = None,
        storage_key: str | None = None,
        metadata: dict | None = None,
    ) -> tuple[dict, bool]:
        """Register a sample. Returns (sample_dict, created).

        Returns created=False if the sample already exists (409).
        This is the idempotency gate for ingest scripts — if created=False,
        skip all columnar and object store writes for this sample.
        """
        resp = self._client.post(
            "/samples",
            json={
                "sample_id": sample_id,
                "instrument": instrument,
                "time_start": time_start.isoformat(),
                "time_end": time_end.isoformat(),
                "quality_flag": quality_flag,
                "alternate_sample_id": alternate_sample_id,
                "storage_key": storage_key,
                "metadata": metadata or {},
            },
        )
        if resp.status_code == 409:
            return self.get_sample(sample_id), False
        resp.raise_for_status()
        return resp.json(), True

    def register_samples_batch(
        self,
        samples: list[dict],
    ) -> tuple[int, int]:
        """Batch-register samples. Returns (registered, skipped)."""
        resp = self._client.post("/samples/batch", json=samples)
        resp.raise_for_status()
        data = resp.json()
        return data["registered"], data["skipped"]

    def get_sample(self, sample_id: str) -> dict | None:
        """Get a sample by ID. Returns None if not found."""
        resp = self._client.get(f"/samples/{sample_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Ingest Tasks
    # ------------------------------------------------------------------

    def register_ingest_task(
        self,
        task_id: str,
        instrument: str | None = None,
    ) -> tuple[dict, bool]:
        """Register an ingest task. Returns (task_dict, created).

        Returns created=False if the task already exists (409).
        This is the idempotency gate — if created=False, skip all
        columnar and object store writes for this task.
        """
        resp = self._client.post(
            "/ingest-tasks",
            json={"task_id": task_id, "instrument": instrument},
        )
        if resp.status_code == 409:
            return self.get_ingest_task(task_id), False
        resp.raise_for_status()
        return resp.json(), True

    def update_ingest_task(self, task_id: str, status: str) -> dict:
        """Update an ingest task's status. Valid: pending, complete, failed."""
        resp = self._client.patch(
            f"/ingest-tasks/{task_id}",
            json={"status": status},
        )
        resp.raise_for_status()
        return resp.json()

    def complete_ingest_task(self, task_id: str) -> dict:
        """Mark an ingest task as complete."""
        return self.update_ingest_task(task_id, "complete")

    def fail_ingest_task(self, task_id: str) -> dict:
        """Mark an ingest task as failed."""
        return self.update_ingest_task(task_id, "failed")

    def delete_ingest_task(self, task_id: str) -> bool:
        """Delete an ingest task. Returns True if deleted, False if not found."""
        resp = self._client.delete(f"/ingest-tasks/{task_id}")
        if resp.status_code == 404:
            return False
        resp.raise_for_status()
        return True

    def get_ingest_task(self, task_id: str) -> dict | None:
        """Get an ingest task by ID. Returns None if not found."""
        resp = self._client.get(f"/ingest-tasks/{task_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Classifier taxonomy
    # ------------------------------------------------------------------

    def register_classifier_taxonomy(
        self,
        classifier: str,
        model_version: str,
        class_names: list[str],
    ) -> tuple[dict, bool]:
        """Register a classifier taxonomy. Returns (taxonomy_dict, created).

        Returns created=False if the (classifier, model_version) already exists
        (409). Batch producers register a taxonomy before ingesting the
        positional score vectors that decode against it.
        """
        resp = self._client.post(
            f"/classifiers/{classifier}/taxonomies",
            json={"model_version": model_version, "class_names": class_names},
        )
        if resp.status_code == 409:
            return self.get_classifier_taxonomy(classifier, model_version), False
        resp.raise_for_status()
        return resp.json(), True

    def get_classifier_taxonomy(
        self, classifier: str, model_version: str
    ) -> dict | None:
        """Get a taxonomy by exact (classifier, model_version). None if absent."""
        resp = self._client.get(
            f"/classifiers/{classifier}/taxonomies/{model_version}"
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
