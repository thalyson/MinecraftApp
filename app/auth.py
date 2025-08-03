"""Authentication utilities for the Stock & Bond trading platform.

This module houses functions to hash passwords using Argon2, create and verify
JSON Web Tokens (JWT), and provide FastAPI dependencies for retrieving
authenticated users from incoming requests. The application stores the access
token inside an HTTP‑only cookie named ``access_token``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from .database import get_session
from .models import User, Role
from .schemas import Token

import yaml
import os

# Load configuration for JWT
def _load_jwt_config() -> dict:
    config_path = os.getenv("CONFIG_FILE", os.path.join(os.path.dirname(__file__), "..", "config.yml"))
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            conf = yaml.safe_load(f)
            return conf.get("jwt", {})
    except FileNotFoundError:
        return {}

jwt_conf = _load_jwt_config()
SECRET_KEY = os.getenv("JWT_SECRET_KEY", jwt_conf.get("secret_key", "secret"))
ALGORITHM = jwt_conf.get("algorithm", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(jwt_conf.get("access_token_expires_minutes", 60))

# Password hashing context
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """Hash a plaintext password using Argon2."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its Argon2 hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token.

    Args:
        data: Dictionary of data to include in the token payload. Must be JSON serializable.
        expires_delta: Optional timedelta specifying expiry; if omitted, uses default.

    Returns:
        Encoded JWT string.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def authenticate_user(session: AsyncSession, email: str, password: str) -> Optional[User]:
    """Authenticate a user by email and password.

    Returns None if authentication fails.
    """
    stmt = select(User).where(User.email == email)
    result = await session.execute(stmt)
    user = result.scalars().first()
    if user and verify_password(password, user.password_hash):
        return user
    return None


async def get_current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User:
    """Dependency to retrieve the current user from the JWT cookie.

    Raises 401 if the token is missing or invalid. If the user cannot be found, raises 401.
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = int(payload.get("user_id"))
    except (JWTError, AttributeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalars().first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency that ensures the current user has admin privileges."""
    if current_user.role != Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return current_user