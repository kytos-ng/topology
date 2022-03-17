"""DB Switch models."""

from typing import List, Optional

from pydantic import validator

from .base import DocumentBaseModel
from .interface import InterfaceModel


class SwitchModel(DocumentBaseModel):
    """SwitchModel."""

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
    metadata: dict = {}
    interfaces: List[InterfaceModel]

    @validator("interfaces", pre=True)
    def validate_interfaces(cls, v, values, **kwargs) -> List[InterfaceModel]:
        """Validate nni."""
        if isinstance(v, dict):
            return list(v.values())
        return v
