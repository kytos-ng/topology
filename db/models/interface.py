"""Interface models."""

from pydantic import BaseModel
from typing import Optional


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
    link: Optional[str]
    switch: str
    type: str
    metadata: dict
    stats: dict
