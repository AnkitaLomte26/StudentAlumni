from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class NamedItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class CatalogCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        value = " ".join(value.split())
        if not value:
            raise ValueError("Name is required.")
        return value


class WorkInput(BaseModel):
    company_id: int = Field(gt=0)
    role: str = Field(min_length=1, max_length=120)
    domain: str = Field(min_length=1, max_length=120)
    start_date: date
    end_date: date | None = None

    @field_validator("role", "domain")
    @classmethod
    def clean_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank.")
        return value

    @model_validator(mode="after")
    def valid_dates(self):
        if self.start_date < date(1950, 1, 1) or self.start_date > date.today():
            raise ValueError("Start date must be between 1950 and today.")
        if self.end_date and (self.end_date < self.start_date or self.end_date > date.today()):
            raise ValueError("End date must be between start date and today.")
        return self


class WorkPublic(WorkInput):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company: NamedItem


class AlumniPublic(BaseModel):
    user_id: int
    name: str
    branch: str | None
    graduation_year: int | None
    bio: str | None
    verification_status: str
    accepting_guidance_requests: bool
    company_relation: str | None = None
    work_experiences: list[WorkPublic]
    skills: list[NamedItem]
    guidance_areas: list[NamedItem]


class SearchPage(BaseModel):
    items: list[AlumniPublic]
    page: int
    page_size: int
    total_results: int
    total_pages: int


class VerificationPublic(BaseModel):
    verification_status: str
    has_proof: bool
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None


class AdminVerification(VerificationPublic):
    user_id: int
    name: str
    email: str
    branch: str | None
    graduation_year: int | None
    proof_media_type: str | None = None


class ReviewInput(BaseModel):
    decision: str
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def valid_decision(self):
        if self.decision not in ("VERIFIED", "REJECTED"):
            raise ValueError("Decision must be VERIFIED or REJECTED.")
        if self.decision == "REJECTED" and not (self.reason or "").strip():
            raise ValueError("Explain why verification was rejected.")
        return self
