"""Authentication: register, login (OAuth2 password flow), current user profile."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas.user import Token, UserCreate, UserRead, UserUpdate
from app.utils.hardening import check_login_allowed, clear_login_failures, record_login_failure
from app.utils.security import create_access_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _token_for(user: User) -> Token:
    return Token(access_token=create_access_token(str(user.id)), user=UserRead.model_validate(user))


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> Token:
    """Create an account and return a bearer token.

    The very first account (or any e-mail listed in ``ADMIN_EMAILS``) is an admin.
    """
    if db.scalar(select(User).where(User.email == payload.email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this e-mail already exists")

    is_first = (db.scalar(select(func.count(User.id))) or 0) == 0
    if not is_first and payload.email not in settings.admin_emails:
        from app.routers.exams import get_branding

        if not get_branding(db).allow_signup:
            raise HTTPException(status_code=403, detail="Self sign-up is disabled. Ask your institution for an account.")
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        is_active=True,
        is_admin=is_first or payload.email in settings.admin_emails,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _token_for(user)


@router.post("/login", response_model=Token)
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> Token:
    """Exchange e-mail (sent as ``username``) and password for a bearer token."""
    email = (form.username or "").strip().lower()
    check_login_allowed(request, email)
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(form.password, user.hashed_password):
        record_login_failure(request, email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect e-mail or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is disabled")
    clear_login_failures(request, email)
    if email in settings.admin_emails and not user.is_admin:
        user.is_admin = True
        db.commit()
        db.refresh(user)
    return _token_for(user)


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.patch("/me", response_model=UserRead)
def update_me(payload: UserUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    """Update the display name and/or password (password change needs the current one)."""
    if "full_name" in payload.model_fields_set:
        user.full_name = (payload.full_name or "").strip() or None
    if payload.new_password:
        if not payload.current_password or not verify_password(payload.current_password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
        user.hashed_password = hash_password(payload.new_password)
    db.commit()
    db.refresh(user)
    return user
