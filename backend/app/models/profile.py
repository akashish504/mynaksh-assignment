from datetime import date, time
from typing import Literal

from pydantic import BaseModel, EmailStr, field_validator, model_validator

from app.profile.validation import validate_dob


class ProfileUpdate(BaseModel):
    """The onboarding form. The sun sign is never accepted from the user."""

    name: str
    dob: date
    birth_time: time | None = None
    birth_time_known: bool
    birth_place: str
    language: Literal["en"] = "en"

    @field_validator("name", "birth_place")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be empty.")
        return value

    @field_validator("dob")
    @classmethod
    def dob_in_range(cls, dob: date) -> date:
        return validate_dob(dob)

    @model_validator(mode="after")
    def birth_time_matches_flag(self) -> "ProfileUpdate":
        if self.birth_time_known and self.birth_time is None:
            raise ValueError("birth_time is required when birth_time_known is true.")
        if not self.birth_time_known:
            # "I don't know" was ticked: ignore any time that was sent.
            self.birth_time = None
        return self


class Zodiac(BaseModel):
    name: str
    element: str | None = None
    traits: list[str] = []


class Profile(BaseModel):
    """The user's profile as stored on the Neo4j User node.

    Fields are optional because a profile can be built up piece by piece
    from chat before the onboarding form is ever submitted.
    """

    name: str | None = None
    dob: date | None = None
    birth_time: time | None = None
    birth_time_known: bool = False
    birth_place: str | None = None
    language: str = "en"
    profile_updated_via: str | None = None
    zodiac: Zodiac | None = None


class MeResponse(BaseModel):
    email: EmailStr
    profile_complete: bool
    profile: Profile | None
