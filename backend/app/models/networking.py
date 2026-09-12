from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class GuidanceRequest(Base):
    __tablename__ = "guidance_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_user_id: Mapped[int] = mapped_column(ForeignKey("student_profiles.user_id", ondelete="RESTRICT"))
    alumni_user_id: Mapped[int] = mapped_column(ForeignKey("alumni_profiles.user_id", ondelete="RESTRICT"))
    guidance_area_id: Mapped[int] = mapped_column(ForeignKey("guidance_areas.id", ondelete="RESTRICT"))
    message: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(20), default="PENDING", server_default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("status IN ('PENDING','ACCEPTED','REJECTED','CANCELLED')", name="ck_request_status"),
        CheckConstraint("length(trim(message)) BETWEEN 1 AND 1000", name="ck_request_message"),
        CheckConstraint("(status = 'PENDING' AND responded_at IS NULL) OR (status <> 'PENDING' AND responded_at IS NOT NULL)", name="ck_request_response_time"),
        UniqueConstraint("id", "student_user_id", "alumni_user_id", name="uq_request_id_pair"),
        Index("uq_pending_request_pair", "student_user_id", "alumni_user_id", unique=True,
              postgresql_where=text("status = 'PENDING'"), sqlite_where=text("status = 'PENDING'")),
        Index("ix_request_student_status_created", "student_user_id", "status", "created_at"),
        Index("ix_request_alumni_status_created", "alumni_user_id", "status", "created_at"),
        Index("ix_request_pair_rejection", "student_user_id", "alumni_user_id", "responded_at",
              postgresql_where=text("status = 'REJECTED'"), sqlite_where=text("status = 'REJECTED'")),
    )


class Connection(Base):
    __tablename__ = "connections"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_user_id: Mapped[int] = mapped_column(ForeignKey("student_profiles.user_id", ondelete="RESTRICT"))
    alumni_user_id: Mapped[int] = mapped_column(ForeignKey("alumni_profiles.user_id", ondelete="RESTRICT"))
    # Null only for a block established before this pair ever connected.
    source_request_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    blocked_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("student_user_id", "alumni_user_id", name="uq_connection_pair"),
        ForeignKeyConstraint(["source_request_id", "student_user_id", "alumni_user_id"],
                             ["guidance_requests.id", "guidance_requests.student_user_id", "guidance_requests.alumni_user_id"],
                             name="fk_connection_source_pair", ondelete="RESTRICT"),
        CheckConstraint("status IN ('ACTIVE','DISCONNECTED','BLOCKED')", name="ck_connection_status"),
        CheckConstraint("status <> 'ACTIVE' OR (source_request_id IS NOT NULL AND connected_at IS NOT NULL AND disconnected_at IS NULL)", name="ck_connection_active"),
        CheckConstraint("status <> 'DISCONNECTED' OR disconnected_at IS NOT NULL", name="ck_connection_disconnected"),
        CheckConstraint("(status = 'BLOCKED' AND blocked_by_user_id IS NOT NULL AND blocked_at IS NOT NULL AND blocked_by_user_id IN (student_user_id, alumni_user_id)) OR (status <> 'BLOCKED' AND blocked_by_user_id IS NULL AND blocked_at IS NULL)", name="ck_connection_block"),
        Index("ix_connection_alumni_status", "alumni_user_id", "status"),
    )


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    request_id: Mapped[int | None] = mapped_column(ForeignKey("guidance_requests.id", ondelete="RESTRICT"))
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id", ondelete="RESTRICT"))
    type: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(String(250))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint("type IN ('REQUEST_RECEIVED','REQUEST_ACCEPTED','REQUEST_REJECTED','MESSAGE_RECEIVED')", name="ck_notification_type"),
        CheckConstraint("(type = 'MESSAGE_RECEIVED' AND conversation_id IS NOT NULL AND request_id IS NULL) OR (type <> 'MESSAGE_RECEIVED' AND request_id IS NOT NULL AND conversation_id IS NULL)", name="ck_notification_target"),
        Index("uq_unread_conversation_notification", "user_id", "conversation_id", unique=True,
              postgresql_where=text("type = 'MESSAGE_RECEIVED' AND is_read = false"), sqlite_where=text("type = 'MESSAGE_RECEIVED' AND is_read = false")),
        UniqueConstraint("user_id", "request_id", "type", name="uq_notification_event"),
        Index("ix_notification_user_read_created", "user_id", "is_read", "created_at"),
    )
