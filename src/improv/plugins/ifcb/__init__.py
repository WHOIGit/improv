"""IFCB-specific provenance plugins and image ID parser.

Not imported by ``improv.plugins`` at core load time. Import from here
explicitly when wiring an IFCB deployment::

    from improv.plugins.ifcb import (
        IFCBFeaturesPlugin,
        IFCBCNNClassificationPlugin,
        IFCBImageIdParser,
    )

Installed as part of the ``improv`` distribution; the ``improv[ifcb]`` extra
is the seam for IFCB-specific third-party dependencies (e.g. a future
ifcb-features port) — see pyproject.toml.
"""

from __future__ import annotations

from improv.plugins.ifcb.classification import (
    IFCBCNNClassificationIndexRecord,
    IFCBCNNClassificationPlugin,
)
from improv.plugins.ifcb.features import (
    IFCBFeaturesIndexRecord,
    IFCBFeaturesPlugin,
    IFCBFeaturesRecord,
)
from improv.plugins.ifcb.image_id import IFCBImageIdParser

__all__ = [
    "IFCBFeaturesPlugin",
    "IFCBFeaturesRecord",
    "IFCBFeaturesIndexRecord",
    "IFCBCNNClassificationPlugin",
    "IFCBCNNClassificationIndexRecord",
    "IFCBImageIdParser",
]
