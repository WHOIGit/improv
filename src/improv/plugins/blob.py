"""Blob provenance plugin (stub).

Handles kind="blob" — segmentation masks and other binary products stored
via amplify-storage-utils. The provenance record payload is a pointer:
an object storage key plus optional metadata (checksum, format, dimensions).

Full implementation deferred until a producer (e.g., ifcb-features) is integrated.
"""

# TODO: implement BlobRecord, BlobPlugin
