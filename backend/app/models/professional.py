from datetime import date, datetime
from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (Index("uq_companies_name_ci", func.lower(name), unique=True),)


class Skill(Base):
    __tablename__ = "skills"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    __table_args__ = (Index("uq_skills_name_ci", func.lower(name), unique=True),)


class GuidanceArea(Base):
    __tablename__ = "guidance_areas"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    __table_args__ = (Index("uq_guidance_areas_name_ci", func.lower(name), unique=True),)


class WorkExperience(Base):
    __tablename__ = "work_experience"
    id: Mapped[int] = mapped_column(primary_key=True)
    alumni_user_id: Mapped[int] = mapped_column(ForeignKey("alumni_profiles.user_id", ondelete="CASCADE"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    role: Mapped[str] = mapped_column(String(120))
    domain: Mapped[str] = mapped_column(String(120))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    company: Mapped[Company] = relationship()
    __table_args__ = (
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_work_dates"),
        Index("ix_work_alumni", "alumni_user_id"),
        Index("ix_work_company_end_alumni", "company_id", "end_date", "alumni_user_id"),
    )


class UserSkill(Base):
    __tablename__ = "user_skills"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)
    __table_args__ = (Index("ix_user_skills_skill_user", "skill_id", "user_id"),)


class AlumniGuidanceArea(Base):
    __tablename__ = "alumni_guidance_areas"
    alumni_user_id: Mapped[int] = mapped_column(ForeignKey("alumni_profiles.user_id", ondelete="CASCADE"), primary_key=True)
    guidance_area_id: Mapped[int] = mapped_column(ForeignKey("guidance_areas.id", ondelete="CASCADE"), primary_key=True)
    __table_args__ = (Index("ix_alumni_guidance_area_user", "guidance_area_id", "alumni_user_id"),)


class AlumniVerification(Base):
    __tablename__ = "alumni_verification"
    alumni_user_id: Mapped[int] = mapped_column(ForeignKey("alumni_profiles.user_id", ondelete="CASCADE"), primary_key=True)
    # Opaque generated basename only; never returned by an API.
    proof_filename: Mapped[str | None] = mapped_column(String(80))
    proof_media_type: Mapped[str | None] = mapped_column(String(40))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    rejection_reason: Mapped[str | None] = mapped_column(String(500))
