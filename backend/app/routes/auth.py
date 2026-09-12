from fastapi import APIRouter, Depends, Request, status
import secrets
from app.services.realtime import manager
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import LoginRequest, RegisterRequest, UserPublic
from app.services.auth import authenticate_user, register_user
from app.utils.deps import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/csrf")
def csrf(request: Request):
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = secrets.token_urlsafe(32)
    return {"csrf_token":request.session["csrf_token"]}


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    return register_user(db, payload)


@router.post("/login", response_model=UserPublic)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload)
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["csrf_token"] = secrets.token_urlsafe(32)
    return user


@router.post("/logout")
async def logout(request: Request):
    user_id = request.session.get("user_id")
    request.session.clear()
    if user_id:
        await manager.close_user(user_id)
    return {"detail": "Logged out."}


@router.get("/me", response_model=UserPublic)
def me(current_user: User = Depends(get_current_user)):
    return current_user
