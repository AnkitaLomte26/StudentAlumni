from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import AccountStatus, AlumniProfile, StudentProfile, User, UserRole, VerificationStatus
from app.schemas import LoginRequest, RegisterRequest
from app.utils.security import hash_password, verify_password


def register_user(db: Session, payload: RegisterRequest) -> User:
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email is already registered.",
        )

    user = User(
        name=payload.name,
        email=str(payload.email).lower(),
        password_hash=hash_password(payload.password),
        role=UserRole(payload.role),
        account_status=AccountStatus.ACTIVE,
    )
    db.add(user)

    try:
        db.flush()
        if payload.role == UserRole.STUDENT.value:
            db.add(
                StudentProfile(
                    user_id=user.id,
                    branch=payload.branch,
                    graduation_year=payload.graduation_year,
                    current_year=payload.current_year,
                    bio=payload.bio,
                )
            )
        else:
            db.add(
                AlumniProfile(
                    user_id=user.id,
                    branch=payload.branch,
                    graduation_year=payload.graduation_year,
                    bio=payload.bio,
                    accepting_guidance_requests=payload.accepting_guidance_requests,
                    verification_status=VerificationStatus.PENDING,
                )
            )
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email is already registered.",
        ) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not complete registration. Please try again.",
        ) from None


def authenticate_user(db: Session, payload: LoginRequest) -> User:
    user = db.query(User).filter(User.email == str(payload.email).lower()).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    if user.account_status != AccountStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is deactivated.",
        )
    return user
