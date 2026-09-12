"""Phase 3 professional profiles, catalogs and private verification metadata."""
from alembic import op
import sqlalchemy as sa

revision = "002_professional_discovery"
down_revision = "001_users_profiles"
branch_labels = None
depends_on = None


def upgrade():
    for name, length in [("companies", 120), ("skills", 80), ("guidance_areas", 80)]:
        columns = [sa.Column("id", sa.Integer(), primary_key=True),
                   sa.Column("name", sa.String(length), nullable=False, unique=True)]
        if name == "companies":
            columns.append(sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
        op.create_table(name, *columns)
        op.create_index("uq_" + name + "_name_ci", name, [sa.text("lower(name)")], unique=True)
    op.create_table("work_experience",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alumni_user_id", sa.Integer(), sa.ForeignKey("alumni_profiles.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("role", sa.String(120), nullable=False), sa.Column("domain", sa.String(120), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False), sa.Column("end_date", sa.Date()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_work_dates"))
    op.create_index("ix_work_alumni", "work_experience", ["alumni_user_id"])
    op.create_index("ix_work_company_end_alumni", "work_experience", ["company_id", "end_date", "alumni_user_id"])
    op.create_table("user_skills",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("skill_id", sa.Integer(), sa.ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True))
    op.create_index("ix_user_skills_skill_user", "user_skills", ["skill_id", "user_id"])
    op.create_table("alumni_guidance_areas",
        sa.Column("alumni_user_id", sa.Integer(), sa.ForeignKey("alumni_profiles.user_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("guidance_area_id", sa.Integer(), sa.ForeignKey("guidance_areas.id", ondelete="CASCADE"), primary_key=True))
    op.create_index("ix_alumni_guidance_area_user", "alumni_guidance_areas", ["guidance_area_id", "alumni_user_id"])
    op.create_table("alumni_verification",
        sa.Column("alumni_user_id", sa.Integer(), sa.ForeignKey("alumni_profiles.user_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("proof_filename", sa.String(80)), sa.Column("proof_media_type", sa.String(40)),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("rejection_reason", sa.String(500)))
    op.create_index("ix_alumni_verification_year", "alumni_profiles", ["verification_status", "graduation_year", "user_id"])


def downgrade():
    op.drop_index("ix_alumni_verification_year", table_name="alumni_profiles")
    for table in ["alumni_verification", "alumni_guidance_areas", "user_skills", "work_experience", "guidance_areas", "skills", "companies"]:
        op.drop_table(table)
