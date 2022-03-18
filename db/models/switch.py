"""DB Switch models."""

from typing import List, Optional

from pydantic import validator

from .base import DocumentBaseModel
from .interface import InterfaceModel


class SwitchModel(DocumentBaseModel):
    """SwitchModel."""

    enabled: bool
    active: bool
    dpid: Optional[str]
    name: Optional[str]
    data_path: Optional[str]
    hardware: Optional[str]
    manufacturer: Optional[str]
    software: Optional[str]
    connection: Optional[str]
    ofp_version: Optional[str]
    serial: Optional[str]
    metadata: dict = {}
    interfaces: List[InterfaceModel] = []

    @validator("dpid", always=True)
    def validate_dpid(cls, v, values, **kwargs) -> bool:
        """Validate dpid."""
        if not v and "id" in values:
            return values["id"]
        return v

    @validator("name", always=True)
    def validate_name(cls, v, values, **kwargs) -> bool:
        """Validate name."""
        if not v and "id" in values:
            return values["id"]
        return v

    @validator("interfaces", pre=True)
    def validate_interfaces(cls, v, values, **kwargs) -> List[InterfaceModel]:
        """Validate interfaces."""
        if isinstance(v, dict):
            return list(v.values())
        return v
