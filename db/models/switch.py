"""DB Switch models."""

from typing import List, Optional

from pydantic import BaseModel
from pydantic import validator
from .interface import InterfaceModel


class SwitchModel(BaseModel):
    """SwitchModel."""

    id: str
    _id: Optional[str]
    enabled: bool
    active: bool
    data_path: str
    dpid: str
    name: str
    hardware: str
    manufacturer: str
    software: str
    connection: Optional[str]
    ofp_version: str
    serial: Optional[str]
    type: str
    metadata: dict
    interfaces: List[InterfaceModel]

    @validator("_id", always=True)
    def _id_overwrite(cls, v, values, **kwargs) -> str:
        if values and values.get("id"):
            v = values["id"]
        return v
