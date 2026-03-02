from __future__ import annotations

"""Simple JWT auth for POC. Not production-grade."""

from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import settings

security = HTTPBearer(auto_error=False)


class TokenData(BaseModel):
    sub: str
    role: str = "viewer"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# Hardcoded users for POC -- replace with DB-backed auth later
POC_USERS = {
    "admin": {"password": "admin", "role": "admin"},
    "ops": {"password": "ops", "role": "ops"},
    "viewer": {"password": "viewer", "role": "viewer"},
}


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> TokenData:
    """Extract user from JWT. If no token provided, default to viewer for POC."""
    if credentials is None:
        return TokenData(sub="anonymous", role="viewer")
    try:
        payload = jwt.decode(
            credentials.credentials, settings.secret_key, algorithms=[settings.algorithm]
        )
        return TokenData(sub=payload.get("sub", "unknown"), role=payload.get("role", "viewer"))
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


def require_role(*roles: str):
    """Dependency that checks the user has one of the given roles."""

    def checker(user: TokenData = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return checker
