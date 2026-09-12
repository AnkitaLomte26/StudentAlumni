from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import AlumniProfile, StudentProfile, User
from app.schemas import AlumniProfileUpdate, StudentProfileUpdate


def get_or_404_student_profile(db: Session, user: User) -> StudentProfile:
    profile = db.get(StudentProfile, user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student profile was not found.",
        )
    return profile


def get_or_404_alumni_profile(db: Session, user: User) -> AlumniProfile:
    profile = db.get(AlumniProfile, user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alumni profile was not found.",
        )
    return profile


def update_student_profile(db: Session, user: User, payload: StudentProfileUpdate) -> StudentProfile:
    profile = get_or_404_student_profile(db, user)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(profile, field, value)
    try:
        db.commit()
        db.refresh(profile)
        return profile
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update the student profile.",
        ) from None


def update_alumni_profile(db: Session, user: User, payload: AlumniProfileUpdate) -> AlumniProfile:
    profile = get_or_404_alumni_profile(db, user)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(profile, field, value)
    try:
        db.commit()
        db.refresh(profile)
        return profile
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update the alumni profile.",
        ) from None
