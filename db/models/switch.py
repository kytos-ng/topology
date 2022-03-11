"""DB Switch models."""

from typing import List, Optional

from pydantic import BaseModel
from pydantic import Field
from .interface import InterfaceModel


class SwitchModel(BaseModel):
    """SwitchModel."""

    id: str = Field(None, alias="_id")
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

    def dict(self) -> dict:
        values = super().dict()
        if "id" in values:
            values["_id"] = values["id"]
        return values
