from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import AccountStatus, UserRole, VerificationStatus


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str
    role: Literal["STUDENT", "ALUMNI"]
    branch: Optional[str] = Field(default=None, max_length=120)
    graduation_year: Optional[int] = Field(default=None, ge=1950, le=2100)
    current_year: Optional[int] = Field(default=None, ge=1, le=8)
    bio: Optional[str] = Field(default=None, max_length=2000)
    accepting_guidance_requests: bool = False

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Name must be at least 2 characters.")
        return cleaned

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters.")
        if not any(ch.isalpha() for ch in value):
            raise ValueError("Password must include at least one letter.")
        if not any(ch.isdigit() for ch in value):
            raise ValueError("Password must include at least one number.")
        return value

    @model_validator(mode="after")
    def role_specific_fields(self) -> "RegisterRequest":
        if self.role == "STUDENT" and self.accepting_guidance_requests:
            raise ValueError("Students cannot set alumni guidance options.")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    role: UserRole
    account_status: AccountStatus


class StudentProfilePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    branch: Optional[str] = None
    graduation_year: Optional[int] = None
    current_year: Optional[int] = None
    bio: Optional[str] = None


class StudentProfileUpdate(BaseModel):
    branch: Optional[str] = Field(default=None, max_length=120)
    graduation_year: Optional[int] = Field(default=None, ge=1950, le=2100)
    current_year: Optional[int] = Field(default=None, ge=1, le=8)
    bio: Optional[str] = Field(default=None, max_length=2000)


class AlumniProfilePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    branch: Optional[str] = None
    graduation_year: Optional[int] = None
    bio: Optional[str] = None
    accepting_guidance_requests: bool
    verification_status: VerificationStatus


class AlumniProfileUpdate(BaseModel):
    branch: Optional[str] = Field(default=None, max_length=120)
    graduation_year: Optional[int] = Field(default=None, ge=1950, le=2100)
    bio: Optional[str] = Field(default=None, max_length=2000)
    accepting_guidance_requests: Optional[bool] = None


class MessageResponse(BaseModel):
    detail: str
    created_at: Optional[datetime] = None
