"""Auth endpoints: register, login, me."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas.auth import AuthResponse, LoginRequest, RegisterRequest, TokenResponse, UserOut
from ..security import create_access_token, hash_password, verify_password
from .deps import get_current_user, rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    rate_limit(request, limit=10)
    email = body.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(email=email, name=body.name.strip(),
                password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return _auth_response(user)


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    rate_limit(request, limit=15)
    email = body.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return _auth_response(user)


@router.get("/me", response_model=UserOut)
def me(current: User = Depends(get_current_user)):
    return current


def _auth_response(user: User) -> AuthResponse:
    token, expires_in = create_access_token(user.id, user.email)
    return AuthResponse(
        token=TokenResponse(access_token=token, expires_in=expires_in),
        user=UserOut.model_validate(user),
    )