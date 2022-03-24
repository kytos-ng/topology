"""DB Interface models."""

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
    nni: bool = False
    lldp: bool
    link: Optional[str]
    metadata: dict = {}
