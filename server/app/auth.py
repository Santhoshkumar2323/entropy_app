from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import settings
from .db import db

router = APIRouter(prefix="/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)

COOKIE = "token"
USER_COLS = "id, username, email, display_name, bio"


class RegisterIn(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_]{3,20}$")
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)
    password: str = Field(min_length=8, max_length=72)


class LoginIn(BaseModel):
    email: str
    password: str


def _pw(password: str) -> bytes:
    return password.encode()[:72]  # bcrypt only reads 72 bytes


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_pw(password), bcrypt.gensalt()).decode()


def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(_pw(password), hashed.encode())


def _set_cookie(response: Response, user_id: int) -> None:
    expires = timedelta(hours=settings.JWT_EXPIRE_HOURS)
    token = jwt.encode(
        {"sub": str(user_id), "exp": datetime.now(timezone.utc) + expires},
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        max_age=int(expires.total_seconds()),
        path="/",
    )


def _user_from_request(request: Request):
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    try:
        data = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        user_id = int(data["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
    with db() as conn:
        return conn.execute(
            f"SELECT {USER_COLS} FROM users WHERE id = %s", (user_id,)
        ).fetchone()


def optional_user(request: Request):
    """Logged-in user or None. Used by endpoints that work for guests too."""
    return _user_from_request(request)


def current_user(request: Request):
    user = _user_from_request(request)
    if not user:
        raise HTTPException(401, "Not authenticated")
    return user


@router.post("/register", status_code=201)
def register(body: RegisterIn, response: Response):
    try:
        with db() as conn:
            user = conn.execute(
                f"""INSERT INTO users (username, email, password_hash, display_name)
                    VALUES (%s, %s, %s, %s) RETURNING {USER_COLS}""",
                (body.username, body.email, hash_password(body.password), body.username),
            ).fetchone()
    except UniqueViolation:
        raise HTTPException(409, "Username or email already in use")
    _set_cookie(response, user["id"])
    return user


@router.post("/login")
@limiter.limit(settings.LOGIN_RATE_LIMIT)
def login(request: Request, body: LoginIn, response: Response):
    with db() as conn:
        row = conn.execute(
            f"SELECT {USER_COLS}, password_hash FROM users WHERE email = %s",
            (body.email,),
        ).fetchone()
    if not row or not check_password(body.password, row["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    row.pop("password_hash")
    _set_cookie(response, row["id"])
    return row


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user=Depends(current_user)):
    return user