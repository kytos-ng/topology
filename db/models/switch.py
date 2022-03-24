"""DB Switch models."""

from typing import List, Optional

from pydantic import validator

from .base import DocumentBaseModel
from .interface import InterfaceModel


class SwitchModel(DocumentBaseModel):
    """SwitchModel."""

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
    interfaces: List[InterfaceModel] = []

    @validator("interfaces", pre=True)
    def preset_interfaces(cls, v, values, **kwargs) -> List[InterfaceModel]:
        """Preset interfaces."""
        if isinstance(v, dict):
            return list(v.values())
        return v
