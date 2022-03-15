"""DB Document base models."""

from pydantic import BaseModel
from pydantic import Field


class DocumentBaseModel(BaseModel):
    """DocumentBaseModel."""

    id: str = Field(None, alias="_id")

    def dict(self) -> dict:
        values = super().dict()
        if "id" in values and values["id"]:
            values["_id"] = values["id"]
        return values
