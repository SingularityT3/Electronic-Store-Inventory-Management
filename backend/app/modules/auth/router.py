"""HTTP routes for the `auth` module: login, logout, current user, password reset."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.modules.audit import audit_service
from app.modules.auth._internal.dependencies import utcnow
from app.modules.auth._internal.login import LoginStatus, authenticate
from app.modules.auth._internal.mail import send_reset_email
from app.modules.auth._internal.models import User
from app.modules.auth._internal.permissions import permissions_for, signed_in
from app.modules.auth._internal.reset import confirm_reset, request_reset
from app.modules.auth._internal.sessions import SESSION_COOKIE, create_session, revoke_session
from app.modules.auth.service import CurrentUser, Permission

router = APIRouter(prefix="/auth", tags=["auth"])

INVALID_CREDENTIALS = "Invalid username or password"
ACCOUNT_LOCKED = "This account is locked. Try again later or ask an administrator to unlock it."
ACCOUNT_DISABLED = "This account is disabled. Contact an administrator."
RESET_REQUESTED = (
    "If the account exists and has an email address, a password reset link has been sent to it."
)
RESET_INVALID = "This reset link is invalid or has expired."

DbSession = Annotated[Session, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]


class LoginRequest(BaseModel):
    username: str = Field(max_length=254, description="Username or email")
    password: str = Field(max_length=1024)


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    location_id: int | None
    permissions: list[Permission]


class ResetRequest(BaseModel):
    username: str = Field(max_length=254, description="Username or email")


class ResetConfirm(BaseModel):
    token: str = Field(max_length=200)
    new_password: str = Field(min_length=8, max_length=1024)


class Message(BaseModel):
    detail: str


def _user_out(user: User | CurrentUser) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        location_id=user.location_id,
        permissions=permissions_for(user.role),
    )


@router.post(
    "/login",
    responses={401: {"model": Message}, 403: {"model": Message}, 423: {"model": Message}},
)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
) -> UserOut:
    now = utcnow()
    if old_token := request.cookies.get(SESSION_COOKIE):
        revoke_session(db, old_token)
    outcome = authenticate(db, body.username, body.password, settings, now)
    token = create_session(db, outcome.user, settings, now) if outcome.user else None
    db.commit()

    if outcome.status is LoginStatus.LOCKED:
        raise HTTPException(status.HTTP_423_LOCKED, ACCOUNT_LOCKED)
    if outcome.status is LoginStatus.DISABLED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, ACCOUNT_DISABLED)
    if outcome.user is None or token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_CREDENTIALS)

    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )
    return _user_out(outcome.user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: DbSession) -> None:
    """End the session on the server and clear the cookie. Safe to call when signed out."""
    if token := request.cookies.get(SESSION_COOKIE):
        user_id = revoke_session(db, token)
        if user_id is not None:
            user = db.get(User, user_id)
            audit_service.record(
                db,
                module="auth",
                action="logout",
                user_id=user_id,
                username=user.username if user else None,
                entity_type="user",
                entity_id=str(user_id),
                details="Signed out",
            )
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", responses={401: {"model": Message}})
def me(user: Annotated[CurrentUser, Depends(signed_in)]) -> UserOut:
    return _user_out(user)


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
def password_reset_request(
    body: ResetRequest, background: BackgroundTasks, db: DbSession, settings: AppSettings
) -> Message:
    email = request_reset(db, body.username, settings, utcnow())
    db.commit()
    if email is not None:
        # Sent after the response, so its timing does not reveal whether the account exists.
        background.add_task(send_reset_email, settings, email.to, email.link)
    return Message(detail=RESET_REQUESTED)


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={400: {"model": Message}},
)
def password_reset_confirm(body: ResetConfirm, db: DbSession) -> None:
    if not confirm_reset(db, body.token, body.new_password, utcnow()):
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, RESET_INVALID)
    db.commit()
