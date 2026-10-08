"""The JSON the extraction LLM returns."""

from typing import Literal

from pydantic import BaseModel


class ExtractedAttribute(BaseModel):
    # Provider-enforced JSON schemas do not allow a free-form map, so attributes
    # arrive as a list of name/value pairs and are turned into a dict when stored.
    name: str
    value: str


class ExtractedItem(BaseModel):
    action: Literal["create", "update", "skip"]
    # The existing memory being changed, when action is "update".
    target_id: str | None
    kind: Literal["goal", "interest", "preference", "memory", "profile_correction"]
    title: str
    text: str
    life_area: str
    attributes: list[ExtractedAttribute]
    # Only for kind = "profile_correction".
    profile_field: Literal["name", "dob", "birth_time", "birth_place"] | None
    profile_value: str | None
    confidence: float
    importance: float


class ExtractionOutput(BaseModel):
    items: list[ExtractedItem]
