"""Interface models."""

from pydantic import BaseModel
from typing import Optional
from pydantic import validator


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
    nni: bool
    lldp: bool
    link: Optional[str]
    switch: str
    type: str
    metadata: dict = {}
    stats: dict = {}

    @validator("nni")
    def validate_nni(cls, v, values, **kwargs) -> bool:
        """Validate nni."""
        if not v ^ values["uni"]:
            raise ValueError("An interface must be either an UNI or NNI")
        return v
