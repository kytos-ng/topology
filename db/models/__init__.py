"""DB models."""
# pylint: disable=unused-argument,no-self-argument,invalid-name,
# pylint: disable=no-name-in-module

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, Field, field_validator
from typing_extensions import Annotated


class DocumentBaseModel(BaseModel):
    """DocumentBaseModel."""

    id: str = Field(None, alias="_id")
    inserted_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def model_dump(self, **kwargs) -> dict:
        """Model to dict."""
        values = super().model_dump(**kwargs)
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
    speed: Optional[float]
    port_number: int
    name: str
    nni: bool = False
    lldp: bool
    switch: str
    link: Optional[str] = None
    link_side: Optional[str] = None
    metadata: dict = {}
    updated_at: Optional[datetime] = None


class SwitchDoc(DocumentBaseModel):
    """Switch DB Document Model."""

    enabled: bool
    data_path: Optional[str] = None
    hardware: Optional[str] = None
    manufacturer: Optional[str] = None
    software: Optional[str] = None
    connection: Optional[str] = None
    ofp_version: Optional[str] = None
    serial: Optional[str] = None
    metadata: dict = {}
    interfaces: list[InterfaceSubDoc] = []

    @field_validator("interfaces", mode="before")
    def preset_interfaces(cls, v, values, **kwargs) -> list[InterfaceSubDoc]:
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
    endpoints: Annotated[list[InterfaceIdSubDoc],
                         Field(min_length=2, max_length=2)]

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

    available_tags: Dict[str, list[list[int]]]
    tag_ranges: Dict[str, list[list[int]]]
    special_available_tags: Dict[str, list[str]]
    special_tags: Dict[str, list[str]]
