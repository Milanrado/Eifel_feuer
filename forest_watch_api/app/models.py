from __future__ import annotations

from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class BBoxModel(BaseModel):
    """WGS84 bbox in the order [west, south, east, north]."""

    bbox: tuple[float, float, float, float] = Field(
        description="WGS84 bounding box [west, south, east, north]"
    )

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: tuple[float, float, float, float]):
        west, south, east, north = value
        if not (-180 <= west < east <= 180):
            raise ValueError("bbox longitude must satisfy -180 <= west < east <= 180")
        if not (-90 <= south < north <= 90):
            raise ValueError("bbox latitude must satisfy -90 <= south < north <= 90")
        return value


class NisarSearchRequest(BBoxModel):
    start: date = Field(description="Acquisition start date (UTC)")
    end: date = Field(description="Acquisition end date (UTC)")
    processing_level: Literal["SME2"] = "SME2"
    data_maturity: Literal["VALIDATED", "PROVISIONAL", "BETA"] | None = None
    direction: Literal["ASCENDING", "DESCENDING"] | None = None
    max_results: int = Field(default=25, ge=1, le=100)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start > self.end:
            raise ValueError("start must be on or before end")
        if (self.end - self.start).days > 730:
            raise ValueError("Search window is limited to 730 days")
        return self


class MoistureRequest(BBoxModel):
    granule_id: str = Field(min_length=10, max_length=200)
    max_points: int = Field(default=2500, ge=100, le=10000)
    include_unrecommended: bool = False

    @model_validator(mode="after")
    def limit_spatial_request(self):
        west, south, east, north = self.bbox
        if east - west > 2.0 or north - south > 2.0:
            raise ValueError("Moisture requests are limited to 2 degrees per bbox axis; use smaller AOIs")
        return self


class SceneResponse(BaseModel):
    granule_id: str
    start_time: str | None = None
    stop_time: str | None = None
    processing_level: str | None = None
    data_maturity: str | None = None
    direction: str | None = None
    path_number: int | None = None
    size_bytes: int | None = None


class MoistureChangeRequest(BBoxModel):
    granule_before: str = Field(min_length=10, max_length=200)
    granule_after: str = Field(min_length=10, max_length=200)
    max_points: int = Field(default=10000, ge=100, le=10000)

    @model_validator(mode="after")
    def limit_spatial_request(self):
        west, south, east, north = self.bbox
        if east - west > 2.0 or north - south > 2.0:
            raise ValueError("Limited to 2 degrees per bbox axis; use smaller AOIs")
        return self
