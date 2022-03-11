"""Interface models."""

from pydantic import BaseModel
from typing import Optional


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
    link_pair: Optional[LinkPairModel]
    switch: str
    type: str
    metadata: dict
    stats: dict
