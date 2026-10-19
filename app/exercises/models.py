from typing import Literal

from pydantic import BaseModel, Field


class Media(BaseModel):
    id: int | None = None
    kind: Literal["image", "video"]
    url: str
    thumb_url: str | None = None
    is_main: bool = False
    license: str
    license_url: str | None = None
    author: str | None = None


class Exercise(BaseModel):
    id: int | None = None
    source: str
    source_id: str
    sources: list[str] = Field(default_factory=list)
    name: str
    name_en: str | None = None
    kind: str = "other"
    region: str | None = None
    muscles_primary: list[str] = Field(default_factory=list)
    muscles_secondary: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    level: str | None = None
    instructions: str | None = None
    instructions_lang: str = "fr"
    license: str
    license_url: str | None = None
    author: str | None = None
    media: list[Media] = Field(default_factory=list)
