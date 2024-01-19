"""DB models."""
# pylint: disable=unused-argument,no-self-argument,invalid-name,
# pylint: disable=no-name-in-module

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, conlist, validator


class DocumentBaseModel(BaseModel):
    """DocumentBaseModel."""

    id: str = Field(None, alias="_id")
    inserted_at: Optional[datetime]
    updated_at: Optional[datetime]

    def dict(self, **kwargs) -> dict:
        """Model to dict."""
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
    mac: str
    speed: float
    port_number: int
    name: str
    nni: bool = False
    lldp: bool
    switch: str
    link: Optional[str]
    link_side: Optional[str]
    metadata: dict = {}
    updated_at: Optional[datetime]


class SwitchDoc(DocumentBaseModel):
    """Switch DB Document Model."""

    enabled: bool
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

    @staticmethod
    def projection() -> dict:
        """Base projection of this model."""
        return {
            "_id": 0,
            "id": 1,
            "enabled": 1,
            "data_path": 1,
            "hardware": 1,
            "manufacturer": 1,
            "software": 1,
            "connection": 1,
            "ofp_version": 1,
            "serial": 1,
            "metadata": 1,
            "interfaces": {
                "$arrayToObject": {
                    "$map": {
                        "input": "$interfaces",
                        "as": "intf",
                        "in": {"k": "$$intf.id", "v": "$$intf"},
                    }
                }
            },
            "updated_at": 1,
            "inserted_at": 1,
        }


class InterfaceIdSubDoc(BaseModel):
    """InterfaceId DB SubDocument Model."""

    id: str


class LinkDoc(DocumentBaseModel):
    """Link DB Document Model."""

    enabled: bool
    metadata: dict = {}
    endpoints: conlist(InterfaceIdSubDoc, min_items=2, max_items=2)

    @staticmethod
    def projection() -> dict:
        """Base projection of this model."""
        return {
            "_id": 0,
            "id": 1,
            "enabled": 1,
            "metadata": 1,
            "endpoint_a": {"$first": "$endpoints"},
            "endpoint_b": {"$last": "$endpoints"},
            "updated_at": 1,
            "inserted_at": 1,
        }


class InterfaceDetailDoc(DocumentBaseModel):
    """InterfaceDetail DB Document Model."""

    available_tags: Dict[str, List[List[int]]]
    tag_ranges: Dict[str, List[List[int]]]
    special_available_tags: Dict[str, List[str]]
    special_tags: Dict[str, List[str]]
