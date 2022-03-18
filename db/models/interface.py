"""DB Interface models."""

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
    nni: bool = False
    uni: Optional[bool]
    lldp: bool
    link: Optional[str]
    switch: str
    metadata: dict = {}
    stats: dict = {}

    @validator("uni", always=True)
    def validate_uni(cls, v, values, **kwargs) -> bool:
        """Validate uni."""
        if v is None:
            return not values["nni"]
        if not (v ^ values["nni"]):
            raise ValueError("An interface must be either an UNI or NNI")
        return v
