from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User
from app.auth import current_user, hash_password, issue_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=200)

@router.post("/register")
def register(body: Credentials, db: Session = Depends(get_db)):
    email = body.email.lower()
    if "@" not in email:
        raise HTTPException(422, "A valid email is required")
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(409, "An account with this email already exists")
    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user); db.commit(); db.refresh(user)
    return {"access_token": issue_token(user), "token_type": "bearer", "user": {"id": user.id, "email": user.email}}

@router.post("/login")
def login(body: Credentials, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=body.email.lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    return {"access_token": issue_token(user), "token_type": "bearer", "user": {"id": user.id, "email": user.email}}

@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email}
