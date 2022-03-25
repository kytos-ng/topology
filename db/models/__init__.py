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


class InterfaceSubDoc(BaseModel):
    """Interface DB SubDocument Model."""

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
    updated_at: Optional[datetime]


class SwitchDoc(DocumentBaseModel):
    """Switch DB Document Model."""

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
    interfaces: List[InterfaceSubDoc] = []

    @validator("interfaces", pre=True)
    def preset_interfaces(cls, v, values, **kwargs) -> List[InterfaceSubDoc]:
        """Preset interfaces."""
        if isinstance(v, dict):
            return list(v.values())
        return v


class LinkDoc(DocumentBaseModel):
    """Link DB Document Model."""

    enabled: bool
    active: bool
    metadata: dict = {}
    endpoints: conlist(InterfaceSubDoc, min_items=2, max_items=2)


class InterfaceDetailDoc(DocumentBaseModel):
    """InterfaceDetail DB Document Model."""

    available_vlans: List[int]
