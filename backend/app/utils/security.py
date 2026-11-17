"""Password hashing, JWT creation/validation and FastAPI auth dependencies.

Hashing goes straight through the ``bcrypt`` package (passlib 1.7.4 is broken
with bcrypt >= 4.1, so it is deliberately not used here).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from jwt import InvalidTokenError as JWTError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User

logger = logging.getLogger(__name__)

TOKEN_URL = "/api/v1/auth/login"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=TOKEN_URL)
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl=TOKEN_URL, auto_error=False)

# bcrypt silently ignores (or, since bcrypt 4.1, rejects) input beyond 72 bytes.
_BCRYPT_MAX_BYTES = 72


def _password_bytes(password: str) -> bytes:
    """Encode a password as UTF-8 and truncate it to bcrypt's 72-byte limit."""
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt and return the hash as a UTF-8 string."""
    hashed = bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Return True when ``password`` matches the stored bcrypt ``hashed`` value.

    Malformed hashes never raise; they simply fail verification.
    """
    if not password or not hashed:
        return False
    try:
        return bcrypt.checkpw(_password_bytes(password), hashed.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        logger.warning("Password verification hit a malformed hash: %s", exc)
        return False


def create_access_token(sub: str, expires_minutes: int | None = None) -> str:
    """Create a signed JWT whose ``sub`` claim is ``sub``.

    ``expires_minutes`` defaults to ``settings.JWT_EXPIRE_MINUTES``.
    """
    minutes = settings.JWT_EXPIRE_MINUTES if expires_minutes is None else expires_minutes
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload: dict[str, Any] = {"sub": sub, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT, returning its claims. Raises ``jwt.InvalidTokenError`` on failure."""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


def _credentials_exception(detail: str = "Could not validate credentials") -> HTTPException:
    """Build the standard 401 response used by the auth dependencies."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _user_from_token(token: str, db: Session) -> User | None:
    """Resolve the active ``User`` referenced by ``token``; None when invalid or unknown."""
    try:
        payload = decode_access_token(token)
    except JWTError as exc:
        logger.debug("JWT rejected: %s", exc)
        return None
    sub = payload.get("sub")
    if sub is None:
        return None
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency returning the authenticated user, or raising HTTP 401."""
    user = _user_from_token(token, db)
    if user is None:
        raise _credentials_exception()
    return user


def get_current_user_optional(
    token: str | None = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
) -> User | None:
    """FastAPI dependency returning the user when a valid bearer token is present, else None.

    Never raises 401: a missing or invalid token simply yields ``None``.
    """
    if not token:
        return None
    return _user_from_token(token, db)


def require_admin(user: User = Depends(get_current_user)) -> User:
    """FastAPI dependency that only lets administrators through (HTTP 403 otherwise)."""
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return user
