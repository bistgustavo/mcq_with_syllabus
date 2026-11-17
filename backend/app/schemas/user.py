"""User and authentication-token schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserCreate(BaseModel):
    """Payload for registering a new user.

    E-mail validation is intentionally lightweight (``email-validator`` is not
    in requirements.txt): the address is trimmed, lower-cased and must contain
    a non-empty local part and domain separated by ``@``.
    """

    email: str = Field(..., min_length=3, max_length=255, examples=["student@example.com"])
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        """At least 8 characters, with letters and digits."""
        if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("password must contain both letters and numbers")
        return value

    @field_validator("email")
    @classmethod
    def normalise_email(cls, value: str) -> str:
        """Trim, lower-case and sanity-check the e-mail address."""
        value = value.strip().lower()
        local, sep, domain = value.partition("@")
        if not sep or not local or not domain or any(ch.isspace() for ch in value):
            raise ValueError("must be a valid e-mail address")
        return value

    @field_validator("full_name")
    @classmethod
    def blank_name_to_none(cls, value: str | None) -> str | None:
        """Store an empty display name as NULL rather than an empty string."""
        if value is None:
            return None
        value = value.strip()
        return value or None


class UserRead(BaseModel):
    """Public representation of a user (never exposes the password hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str | None = None
    is_active: bool = True
    is_admin: bool = False
    created_at: datetime | None = None


class Token(BaseModel):
    """Bearer token issued by ``POST /api/v1/auth/login``."""

    access_token: str
    token_type: str = "bearer"
    user: UserRead


class UserUpdate(BaseModel):
    """Self-service profile update."""

    full_name: str | None = Field(default=None, max_length=255)
    current_password: str | None = None
    new_password: str | None = Field(default=None, min_length=8, max_length=128)


class AdminUserUpdate(BaseModel):
    """Admin-only changes to another account."""

    is_active: bool | None = None
    is_admin: bool | None = None
