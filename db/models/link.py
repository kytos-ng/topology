"""Link models."""

from typing import Optional

from pydantic import BaseModel
from pydantic import validator


class LinkModel(BaseModel):
    """Link Model."""

    id: str
    _id: Optional[str]
    enabled: bool
    active: bool
    metadata: dict

    @validator("_id", always=True)
    def _id_overwrite(cls, v, values, **kwargs) -> str:
        if values and values.get("id"):
            v = values["id"]
        return v
