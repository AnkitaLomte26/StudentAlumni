from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas.professional import NamedItem

RequestStatus = Literal["PENDING", "ACCEPTED", "REJECTED", "CANCELLED"]
ConnectionStatus = Literal["ACTIVE", "DISCONNECTED", "BLOCKED"]


class RequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alumni_user_id: int = Field(gt=0)
    guidance_area_id: int = Field(gt=0)
    message: str = Field(min_length=1, max_length=1000)

    @field_validator("message")
    @classmethod
    def meaningful(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Explain what guidance you are looking for.")
        return value


class BlockCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    other_user_id: int = Field(gt=0)


class PersonPublic(BaseModel):
    user_id: int
    name: str
    role: str
    branch: str | None
    graduation_year: int | None
    bio: str | None
    skills: list[NamedItem]


class RequestPublic(BaseModel):
    id: int
    student: PersonPublic
    alumni: PersonPublic
    guidance_area: NamedItem
    message: str
    status: RequestStatus
    created_at: datetime
    responded_at: datetime | None
    cooldown_until: datetime | None


class RequestPage(BaseModel):
    items: list[RequestPublic]
    page: int
    page_size: int
    total_results: int
    total_pages: int
    pending_count: int
    pending_limit: int


class ConnectionPublic(BaseModel):
    id: int
    conversation_id: int | None = None
    student: PersonPublic
    alumni: PersonPublic
    source_request_id: int | None
    status: ConnectionStatus
    connected_at: datetime | None
    updated_at: datetime
    disconnected_at: datetime | None
    blocked_by_user_id: int | None
    blocked_at: datetime | None


class ConnectionPage(BaseModel):
    items: list[ConnectionPublic]
    page: int
    page_size: int
    total_results: int
    total_pages: int


class NotificationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    request_id: int | None
    conversation_id: int | None = None
    type: str
    message: str
    is_read: bool
    created_at: datetime


class NotificationPage(BaseModel):
    items: list[NotificationPublic]
    unread_count: int
    page: int
    page_size: int
    total_results: int
    total_pages: int
