"""Human annotation schemas (stubs).

Machine classification payloads live in ``improv.plugins.classification``
(MachineClassificationRecord). This module holds only the human-annotation
region stubs (RegionDescriptor, FullFrameRegion, BBoxRegion), defined as data
classes for reference. Full plugin implementation deferred until annotation
tool integration (Photic / LabelStudio).
"""

from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Human annotation stubs (no plugin yet)
# ---------------------------------------------------------------------------

@dataclass
class FullFrameRegion:
    """The entire image frame is the annotated region."""
    pass


@dataclass
class BBoxRegion:
    """Axis-aligned bounding box region."""
    x: int
    y: int
    width: int
    height: int


# RegionDescriptor is the union of region types
RegionDescriptor = FullFrameRegion | BBoxRegion
