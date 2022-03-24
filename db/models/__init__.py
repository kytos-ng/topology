"""DB models."""

from typing import List, Optional
from datetime import datetime

from pydantic import BaseModel
from pydantic import conlist
from pydantic import Field
from pydantic import validator


class DocumentBaseModel(BaseModel):
    """DocumentBaseModel."""

    id: str = Field(None, alias="_id")
    inserted_at: Optional[datetime]
    updated_at: Optional[datetime]

    def dict(self, **kwargs) -> dict:
        values = super().dict(**kwargs)
        if "id" in values and values["id"]:
            values["_id"] = values["id"]
        if "exclude" in kwargs and "_id" in kwargs["exclude"]:
            values.pop("_id")
        return values


class InterfaceDB(BaseModel):
    """Interface DB Model."""

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


class SwitchDB(DocumentBaseModel):
    """Switch DB Model."""

    enabled: bool
    active: bool
    data_path: Optional[str]
    hardware: Optional[str]
    manufacturer: Optional[str]
    software: Optional[str]
    connection: Optional[str]
    ofp_version: Optional[str]
    serial: Optional[str]
    metadata: dict = {}
    interfaces: List[InterfaceDB] = []

    @validator("interfaces", pre=True)
    def preset_interfaces(cls, v, values, **kwargs) -> List[InterfaceDB]:
        """Preset interfaces."""
        if isinstance(v, dict):
            return list(v.values())
        return v


class LinkDB(DocumentBaseModel):
    """Link DB Model."""

    enabled: bool
    active: bool
    metadata: dict = {}
    endpoints: conlist(InterfaceDB, min_items=2, max_items=2)
