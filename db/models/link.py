"""Link models."""

from .base import DocumentBaseModel
from .interface import InterfaceModel


class LinkModel(DocumentBaseModel):
    """Link Model."""

    enabled: bool
    active: bool
    metadata: dict = {}
    endpoint_a: InterfaceModel
    endpoint_b: InterfaceModel
