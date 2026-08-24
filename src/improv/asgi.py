"""ASGI entrypoint for the improv REST service.

Run with::

    uvicorn improv.asgi:app --host 0.0.0.0 --port 8000 --workers 4 \
            --proxy-headers --forwarded-allow-ips=<proxy-ip>

Configuration comes entirely from the environment — see improv.config for the
full variable list. ``uvicorn --factory`` is not usable here because
``create_app`` takes a config argument, hence this module-level object.

Each worker process imports this module independently, so each gets its own
columnar store connection and its own sessionmaker. That is intended.
"""

from __future__ import annotations

from improv.api.app import create_app
from improv.config import load_config

app = create_app(load_config())
