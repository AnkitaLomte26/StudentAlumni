from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import (
    AlumniProfilePublic,
    AlumniProfileUpdate,
    StudentProfilePublic,
    StudentProfileUpdate,
)
from app.services import profiles as profile_service
from app.utils.deps import require_alumni, require_student

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.get("/student/me", response_model=StudentProfilePublic)
def get_student_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student),
):
    return profile_service.get_or_404_student_profile(db, current_user)


@router.put("/student/me", response_model=StudentProfilePublic)
def update_student_profile(
    payload: StudentProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student),
):
    return profile_service.update_student_profile(db, current_user, payload)


@router.get("/alumni/me", response_model=AlumniProfilePublic)
def get_alumni_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_alumni),
):
    return profile_service.get_or_404_alumni_profile(db, current_user)


@router.put("/alumni/me", response_model=AlumniProfilePublic)
def update_alumni_profile(
    payload: AlumniProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_alumni),
):
    return profile_service.update_alumni_profile(db, current_user, payload)
