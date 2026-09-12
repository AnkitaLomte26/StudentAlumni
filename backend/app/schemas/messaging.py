from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas.networking import PersonPublic, ConnectionStatus


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def meaningful(cls, value):
        value = value.strip()
        if not value or "\x00" in value:
            raise ValueError("Enter a message without null characters.")
        return value


class ReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    through_message_id: int = Field(gt=0)


class MessagePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    conversation_id: int
    sender_user_id: int
    content: str
    created_at: datetime
    read_at: datetime | None


class ConversationPublic(BaseModel):
    id: int
    connection_id: int
    connection_status: ConnectionStatus
    other_participant: PersonPublic
    created_at: datetime
    updated_at: datetime
    last_message_preview: str | None
    unread_count: int
    can_send: bool


class ConversationPage(BaseModel):
    items: list[ConversationPublic]
    page: int
    page_size: int
    total_results: int
    total_pages: int


class MessagePage(BaseModel):
    items: list[MessagePublic]
    page: int
    page_size: int
    total_results: int
    total_pages: int
    snapshot_id: int | None

