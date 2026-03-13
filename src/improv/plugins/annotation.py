"""Annotation provenance plugin (stub).

Handles kind="machine_annotation" and kind="human_annotation".

machine_annotation: classifier score distribution across all classes,
produced by a classifier run. Payload includes run_id, model_version,
and per-class scores.

human_annotation: discrete label choice with annotator identity and region
descriptor (FullFrameRegion or BBoxRegion). Produced by annotation tools
(Photic for IFCB bulk ROI annotation; LabelStudio for bbox/mask annotation).

Full implementation deferred until annotation tool integration.
"""

# TODO: implement RegionDescriptor, FullFrameRegion, BBoxRegion
# TODO: implement MachineAnnotationRecord, HumanAnnotationRecord
# TODO: implement AnnotationPlugin
