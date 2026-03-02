"""Auth endpoints for POC token generation."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.auth import POC_USERS, TokenResponse, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/token", response_model=TokenResponse)
def login(payload: LoginRequest):
    """Get a JWT token. POC only -- hardcoded users."""
    user = POC_USERS.get(payload.username)
    if not user or user["password"] != payload.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    token = create_access_token({"sub": payload.username, "role": user["role"]})
    return TokenResponse(access_token=token)
