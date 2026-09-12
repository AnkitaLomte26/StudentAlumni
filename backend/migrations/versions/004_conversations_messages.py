"""Phase 5 persistent two-person REST messaging."""
from alembic import op
import sqlalchemy as sa

revision = "004_conversations_messages"
down_revision = "003_guidance_connections"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("connection_id", sa.Integer(), sa.ForeignKey("connections.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("connection_id", name="uq_conversation_connection"))
    op.create_table("messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sender_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("content", sa.String(2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("length(trim(content)) BETWEEN 1 AND 2000", name="ck_message_content"))
    op.create_index("ix_message_conversation_created", "messages", ["conversation_id", "created_at", "id"])
    op.create_index("ix_message_conversation_unread", "messages", ["conversation_id", "sender_user_id"],
                    postgresql_where=sa.text("read_at IS NULL"), sqlite_where=sa.text("read_at IS NULL"))
    op.alter_column("notifications", "request_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("notifications", sa.Column("conversation_id", sa.Integer()))
    op.create_foreign_key("fk_notification_conversation", "notifications", "conversations", ["conversation_id"], ["id"], ondelete="RESTRICT")
    op.drop_constraint("ck_notification_type", "notifications", type_="check")
    op.create_check_constraint("ck_notification_type", "notifications",
        "type IN ('REQUEST_RECEIVED','REQUEST_ACCEPTED','REQUEST_REJECTED','MESSAGE_RECEIVED')")
    op.create_check_constraint("ck_notification_target", "notifications",
        "(type = 'MESSAGE_RECEIVED' AND conversation_id IS NOT NULL AND request_id IS NULL) OR (type <> 'MESSAGE_RECEIVED' AND request_id IS NOT NULL AND conversation_id IS NULL)")
    op.create_index("uq_unread_conversation_notification", "notifications", ["user_id","conversation_id"], unique=True,
        postgresql_where=sa.text("type = 'MESSAGE_RECEIVED' AND is_read = false"),
        sqlite_where=sa.text("type = 'MESSAGE_RECEIVED' AND is_read = false"))


def downgrade():
    # Downgrade intentionally removes Phase 5 history; never used for routine deployment.
    op.execute("DELETE FROM notifications WHERE type = 'MESSAGE_RECEIVED'")
    op.drop_index("uq_unread_conversation_notification", table_name="notifications")
    op.drop_constraint("ck_notification_target", "notifications", type_="check")
    op.drop_constraint("ck_notification_type", "notifications", type_="check")
    op.create_check_constraint("ck_notification_type", "notifications",
        "type IN ('REQUEST_RECEIVED','REQUEST_ACCEPTED','REQUEST_REJECTED')")
    op.drop_constraint("fk_notification_conversation", "notifications", type_="foreignkey")
    op.drop_column("notifications", "conversation_id")
    op.alter_column("notifications", "request_id", existing_type=sa.Integer(), nullable=False)
    op.drop_table("messages")
    op.drop_table("conversations")

