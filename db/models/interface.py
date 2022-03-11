"""Interface models."""

from pydantic import BaseModel
from pydantic import conlist


class LinkPairModel(BaseModel):
    """LinkPairModel."""

    id: str
    side: str


class InterfaceModel(BaseModel):
    """Interface Model."""

    id: str
    enabled: bool
    active: bool
    mac: str
    speed: float
    port_number: int
    name: str
    uni: bool
    lldp: bool
    link_pair: conlist(LinkPairModel, min_items=2, max_items=2)
    switch: str
    type: str
    metadata: dict
    stats: dict
