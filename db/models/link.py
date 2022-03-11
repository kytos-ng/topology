"""Link models."""

from pydantic import BaseModel
from pydantic import Field


class LinkModel(BaseModel):
    """Link Model."""

    id: str = Field(None, alias="_id")
    enabled: bool
    active: bool
    metadata: dict

    def dict(self) -> dict:
        values = super().dict()
        if "id" in values:
            values["_id"] = values["id"]
        return values
