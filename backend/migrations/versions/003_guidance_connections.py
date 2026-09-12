"""Phase 4 request history, current relationships, and persistent notifications."""
from alembic import op
import sqlalchemy as sa

revision = "003_guidance_connections"
down_revision = "002_professional_discovery"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("guidance_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_user_id", sa.Integer(), sa.ForeignKey("student_profiles.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("alumni_user_id", sa.Integer(), sa.ForeignKey("alumni_profiles.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("guidance_area_id", sa.Integer(), sa.ForeignKey("guidance_areas.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("message", sa.String(1000), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("responded_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('PENDING','ACCEPTED','REJECTED','CANCELLED')", name="ck_request_status"),
        sa.CheckConstraint("length(trim(message)) BETWEEN 1 AND 1000", name="ck_request_message"),
        sa.CheckConstraint("(status = 'PENDING' AND responded_at IS NULL) OR (status <> 'PENDING' AND responded_at IS NOT NULL)", name="ck_request_response_time"),
        sa.UniqueConstraint("id", "student_user_id", "alumni_user_id", name="uq_request_id_pair"))
    op.create_index("uq_pending_request_pair", "guidance_requests", ["student_user_id", "alumni_user_id"],
        unique=True, postgresql_where=sa.text("status = 'PENDING'"), sqlite_where=sa.text("status = 'PENDING'"))
    op.create_index("ix_request_student_status_created", "guidance_requests", ["student_user_id", "status", "created_at"])
    op.create_index("ix_request_alumni_status_created", "guidance_requests", ["alumni_user_id", "status", "created_at"])
    op.create_index("ix_request_pair_rejection", "guidance_requests", ["student_user_id", "alumni_user_id", "responded_at"],
        postgresql_where=sa.text("status = 'REJECTED'"), sqlite_where=sa.text("status = 'REJECTED'"))
    op.create_table("connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_user_id", sa.Integer(), sa.ForeignKey("student_profiles.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("alumni_user_id", sa.Integer(), sa.ForeignKey("alumni_profiles.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_request_id", sa.Integer()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("disconnected_at", sa.DateTime(timezone=True)),
        sa.Column("blocked_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("blocked_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("student_user_id", "alumni_user_id", name="uq_connection_pair"),
        sa.ForeignKeyConstraint(["source_request_id", "student_user_id", "alumni_user_id"],
            ["guidance_requests.id", "guidance_requests.student_user_id", "guidance_requests.alumni_user_id"],
            name="fk_connection_source_pair", ondelete="RESTRICT"),
        sa.CheckConstraint("status IN ('ACTIVE','DISCONNECTED','BLOCKED')", name="ck_connection_status"),
        sa.CheckConstraint("status <> 'ACTIVE' OR (source_request_id IS NOT NULL AND connected_at IS NOT NULL AND disconnected_at IS NULL)", name="ck_connection_active"),
        sa.CheckConstraint("status <> 'DISCONNECTED' OR disconnected_at IS NOT NULL", name="ck_connection_disconnected"),
        sa.CheckConstraint("(status = 'BLOCKED' AND blocked_by_user_id IS NOT NULL AND blocked_at IS NOT NULL AND blocked_by_user_id IN (student_user_id, alumni_user_id)) OR (status <> 'BLOCKED' AND blocked_by_user_id IS NULL AND blocked_at IS NULL)", name="ck_connection_block"))
    op.create_index("ix_connection_alumni_status", "connections", ["alumni_user_id", "status"])
    op.create_table("notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("guidance_requests.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("type", sa.String(40), nullable=False),
        sa.Column("message", sa.String(250), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("type IN ('REQUEST_RECEIVED','REQUEST_ACCEPTED','REQUEST_REJECTED')", name="ck_notification_type"),
        sa.UniqueConstraint("user_id", "request_id", "type", name="uq_notification_event"))
    op.create_index("ix_notification_user_read_created", "notifications", ["user_id", "is_read", "created_at"])


def downgrade():
    op.drop_table("notifications")
    op.drop_table("connections")
    op.drop_table("guidance_requests")
