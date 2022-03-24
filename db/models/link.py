"""Link models."""

from .base import DocumentBaseModel
from .interface import InterfaceModel
from pydantic import conlist


class LinkModel(DocumentBaseModel):
    """Link Model."""

    enabled: bool
    active: bool
    metadata: dict = {}
    endpoints: conlist(InterfaceModel, min_items=2, max_items=2)
