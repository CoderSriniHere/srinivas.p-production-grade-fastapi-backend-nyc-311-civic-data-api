from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

VALID_BOROUGHS = {"MANHATTAN", "BROOKLYN", "QUEENS", "BRONX", "STATEN ISLAND", "UNKNOWN"}


class ComplaintCreate(BaseModel):
    unique_key: str
    complaint_type: str
    borough: str
    descriptor: str | None = None
    incident_zip: str | None = None
    incident_address: str | None = None
    created_date: datetime

    @field_validator("borough")
    @classmethod
    def normalize_borough(cls, value: str) -> str:
        upper = value.upper()
        if upper not in VALID_BOROUGHS:
            raise ValueError(f"borough must be one of {sorted(VALID_BOROUGHS)}")
        return upper


class ComplaintStatusUpdate(BaseModel):
    status: str


class ComplaintSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    unique_key: str
    agency: str
    complaint_type: str
    status: str
    borough: str
    created_date: datetime


class ComplaintDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    unique_key: str
    agency: str
    complaint_type: str
    descriptor: str | None
    status: str
    borough: str
    incident_zip: str | None
    incident_address: str | None
    created_date: datetime
    closed_date: datetime | None
    resolution_description: str | None


class PaginatedComplaints(BaseModel):
    items: list[ComplaintSummary]
    page: int
    limit: int
    total: int
