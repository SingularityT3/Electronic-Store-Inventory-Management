"""HTTP routes for the `auth` module: login, logout, current user, password reset."""

from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.modules.audit import audit_service
from app.modules.auth._internal.csrf import (
    CSRF_COOKIE,
    clear_csrf_cookie,
    set_csrf_cookie,
)
from app.modules.auth._internal.dependencies import utcnow
from app.modules.auth._internal.login import LoginStatus, authenticate
from app.modules.auth._internal.mail import send_reset_email
from app.modules.auth._internal.models import User
from app.modules.auth._internal.passwords import hash_password
from app.modules.auth._internal.permissions import permissions_for, require, signed_in
from app.modules.auth._internal.reset import confirm_reset, create_invite, request_reset
from app.modules.auth._internal.sessions import (
    SESSION_COOKIE,
    create_session,
    revoke_session,
    revoke_user_sessions,
)
from app.modules.auth._internal.tokens import new_token
from app.modules.auth.service import CurrentUser, LocationValidator, Permission

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


class ManagedUserOut(BaseModel):
    id: int
    full_name: str
    username: str
    email: str | None
    role: Literal["admin", "manager", "staff", "cashier"]
    location_id: int | None
    is_active: bool
    is_locked: bool = False
    """Locked out after repeated failed logins (SRS A-12); an Admin can unlock it early."""


class UserPage(BaseModel):
    users: list[ManagedUserOut]
    total: int
    limit: int
    offset: int


class UserForm(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    username: str | None = Field(default=None, max_length=150)
    email: str | None = Field(default=None, max_length=254)
    role: str | None = None
    location_id: int | None = None
    is_active: bool | None = None


def _default_location_validator(_db: Session, _location_id: int) -> bool:
    return False


_location_validator: LocationValidator = _default_location_validator


def get_location_validator() -> LocationValidator:
    """The composition root supplies stock's public location validator."""
    return _location_validator


def set_location_validator(validator: LocationValidator) -> None:
    global _location_validator
    _location_validator = validator


LocationCheck = Annotated[LocationValidator, Depends(get_location_validator)]


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


def _managed_user(user: User) -> ManagedUserOut:
    out = ManagedUserOut.model_validate(user, from_attributes=True)
    out.is_locked = user.locked_until is not None and user.locked_until > utcnow()
    return out


def _field_error(field: str, message: str, code: int = status.HTTP_422_UNPROCESSABLE_ENTITY):
    raise HTTPException(code, {field: message})


def _validate_form(
    body: UserForm,
    *,
    creating: bool,
    location_check: LocationValidator,
    db: Session,
) -> dict[str, object]:
    values = body.model_dump()
    required = ("full_name", "username", "email", "role") if creating else ()
    required_errors: dict[str, str] = {}
    for field in required:
        value = values[field]
        if not isinstance(value, str) or not value.strip():
            required_errors[field] = "This field is required."
    if required_errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, required_errors)
    for field in ("full_name", "username", "email"):
        if isinstance(values[field], str):
            values[field] = values[field].strip()
    if values["email"] and (
        "@" not in values["email"]
        or values["email"].startswith("@")
        or values["email"].endswith("@")
    ):
        _field_error("email", "Enter a valid email address.")
    if values["role"] is not None and values["role"] not in {
        "admin",
        "manager",
        "staff",
        "cashier",
    }:
        _field_error("role", "Choose a valid role.")
    if values["role"] in {"staff", "cashier"} and values["location_id"] is None:
        _field_error("location_id", "A location is required for Staff and Cashier.")
    if values["location_id"] is not None and not location_check(db, values["location_id"]):
        _field_error("location_id", "Choose an active location.")
    return values


def _duplicate_errors(
    db: Session, *, email: str | None, username: str | None, exclude_id: int | None = None
) -> dict[str, str]:
    errors: dict[str, str] = {}
    conditions = []
    if email:
        conditions.append((func.lower(User.email) == email.lower(), "email"))
    if username:
        conditions.append((func.lower(User.username) == username.lower(), "username"))
    for condition, field in conditions:
        query = select(User.id).where(condition)
        if exclude_id is not None:
            query = query.where(User.id != exclude_id)
        if db.scalar(query) is not None:
            errors[field] = f"This {field} is already in use."
    return errors


def _snapshot(user: User) -> dict[str, object]:
    return {
        "full_name": user.full_name,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "location_id": user.location_id,
        "is_active": user.is_active,
    }


def _ensure_admin_safety(
    db: Session, actor: CurrentUser, target: User, new_role: str, active: bool
):
    if target.id == actor.id and (not active or new_role != "admin"):
        _field_error(
            "is_active" if not active else "role", "You cannot disable or demote yourself.", 403
        )
    # Only an active Admin counts; editing an already disabled Admin is always allowed.
    if target.role == "admin" and target.is_active and (new_role != "admin" or not active):
        # Lock the active Admins, so two concurrent demotions cannot remove the last one.
        active_admins = db.scalars(
            select(User.id).where(User.role == "admin", User.is_active).with_for_update()
        ).all()
        if len(active_admins) <= 1:
            _field_error(
                "role" if new_role != "admin" else "is_active",
                "The last active Admin cannot be disabled or demoted.",
                409,
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
    set_csrf_cookie(response, settings.cookie_secure)
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
    clear_csrf_cookie(response)


@router.get("/me", responses={401: {"model": Message}})
def me(
    request: Request,
    response: Response,
    user: Annotated[CurrentUser, Depends(signed_in)],
    settings: AppSettings,
) -> UserOut:
    # Sessions that began before CSRF tokens existed get one here.
    if CSRF_COOKIE not in request.cookies:
        set_csrf_cookie(response, settings.cookie_secure)
    return _user_out(user)


@router.get("/users", dependencies=[Depends(require(Permission.USERS_MANAGE))])
def list_users(
    db: DbSession,
    search: Annotated[str | None, Query(max_length=150)] = None,
    status_filter: Annotated[bool | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserPage:
    query = select(User)
    if search:
        term = f"%{search.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(User.full_name).like(term),
                func.lower(User.username).like(term),
                func.lower(User.email).like(term),
            )
        )
    if status_filter is not None:
        query = query.where(User.is_active == status_filter)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    users = db.scalars(query.order_by(User.full_name, User.id).limit(limit).offset(offset)).all()
    return UserPage(
        users=[_managed_user(user) for user in users],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/users/{user_id}", dependencies=[Depends(require(Permission.USERS_MANAGE))])
def get_user(user_id: int, db: DbSession) -> ManagedUserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    return _managed_user(user)


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserForm,
    background: BackgroundTasks,
    db: DbSession,
    settings: AppSettings,
    actor: Annotated[CurrentUser, Depends(require(Permission.USERS_MANAGE))],
    location_check: LocationCheck,
) -> ManagedUserOut:
    values = _validate_form(body, creating=True, location_check=location_check, db=db)
    duplicates = _duplicate_errors(db, email=values["email"], username=values["username"])
    if duplicates:
        raise HTTPException(status.HTTP_409_CONFLICT, duplicates)
    values.pop("is_active", None)
    user = User(
        **values,
        password_hash=hash_password(new_token()),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, {"email": "This email or username is already in use."}
        ) from None
    invite = create_invite(db, user, settings, utcnow())
    audit_service.record(
        db,
        module="auth",
        action="user_created",
        user_id=actor.id,
        username=actor.username,
        entity_type="user",
        entity_id=str(user.id),
        after=_snapshot(user),
    )
    db.commit()
    background.add_task(
        send_reset_email,
        settings,
        invite.to,
        invite.link,
        subject="Set up your ESIMS account",
        introduction="An ESIMS account was created for you.",
    )
    return _managed_user(user)


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    body: UserForm,
    db: DbSession,
    actor: Annotated[CurrentUser, Depends(require(Permission.USERS_MANAGE))],
    location_check: LocationCheck,
) -> ManagedUserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    raw_values = body.model_dump()
    validation_values = UserForm(
        full_name=raw_values["full_name"] or user.full_name,
        username=raw_values["username"] or user.username,
        email=raw_values["email"] or user.email,
        role=raw_values["role"] or user.role,
        location_id=raw_values["location_id"]
        if raw_values["location_id"] is not None
        else user.location_id,
        is_active=raw_values["is_active"]
        if raw_values["is_active"] is not None
        else user.is_active,
    )
    values = _validate_form(validation_values, creating=False, location_check=location_check, db=db)
    if body.location_id is None and body.role is None:
        values["location_id"] = user.location_id
    elif body.location_id is None and body.role not in {"staff", "cashier"}:
        values["location_id"] = None
    if body.is_active is None:
        values["is_active"] = user.is_active
    new_role = str(values.get("role", user.role))
    active = bool(values.get("is_active", user.is_active))
    _ensure_admin_safety(db, actor, user, new_role, active)
    duplicates = _duplicate_errors(
        db,
        email=values.get("email", user.email),
        username=values.get("username", user.username),
        exclude_id=user.id,
    )
    if duplicates:
        raise HTTPException(status.HTTP_409_CONFLICT, duplicates)
    before = _snapshot(user)
    for key, value in values.items():
        setattr(user, key, value)
    db.flush()
    after = _snapshot(user)
    if before != after:
        audit_service.record(
            db,
            module="auth",
            action="user_updated",
            user_id=actor.id,
            username=actor.username,
            entity_type="user",
            entity_id=str(user.id),
            before={key: before[key] for key in before if before[key] != after[key]},
            after={key: after[key] for key in after if before[key] != after[key]},
        )
        if before["role"] != after["role"]:
            audit_service.record(
                db,
                module="auth",
                action="user_role_changed",
                user_id=actor.id,
                username=actor.username,
                entity_type="user",
                entity_id=str(user.id),
                before={"role": before["role"]},
                after={"role": after["role"]},
            )
    db.commit()
    return _managed_user(user)


def _set_active(
    user_id: int,
    db: Session,
    actor: CurrentUser,
    active: bool,
) -> ManagedUserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    _ensure_admin_safety(db, actor, user, user.role, active)
    if user.is_active == active:
        return _managed_user(user)
    before = _snapshot(user)
    user.is_active = active
    if not active:
        revoke_user_sessions(db, user.id)
    audit_service.record(
        db,
        module="auth",
        action="user_reactivated" if active else "user_deactivated",
        user_id=actor.id,
        username=actor.username,
        entity_type="user",
        entity_id=str(user.id),
        before={"is_active": before["is_active"]},
        after={"is_active": active},
    )
    db.commit()
    return _managed_user(user)


@router.post("/users/{user_id}/deactivate")
def deactivate_user(
    user_id: int,
    db: DbSession,
    actor: Annotated[CurrentUser, Depends(require(Permission.USERS_MANAGE))],
) -> ManagedUserOut:
    return _set_active(user_id, db, actor, False)


@router.post("/users/{user_id}/reactivate")
def reactivate_user(
    user_id: int,
    db: DbSession,
    actor: Annotated[CurrentUser, Depends(require(Permission.USERS_MANAGE))],
) -> ManagedUserOut:
    return _set_active(user_id, db, actor, True)


@router.post("/users/{user_id}/unlock")
def unlock_user(
    user_id: int,
    db: DbSession,
    actor: Annotated[CurrentUser, Depends(require(Permission.USERS_MANAGE))],
) -> ManagedUserOut:
    """End a login lockout before it expires (SRS A-12, FR5.2-ST-2)."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    if user.locked_until is None and user.failed_login_count == 0:
        return _managed_user(user)
    before = {"locked_until": user.locked_until, "failed_login_count": user.failed_login_count}
    user.locked_until = None
    user.failed_login_count = 0
    audit_service.record(
        db,
        module="auth",
        action="user_unlocked",
        user_id=actor.id,
        username=actor.username,
        entity_type="user",
        entity_id=str(user.id),
        before=before,
        after={"locked_until": None, "failed_login_count": 0},
    )
    db.commit()
    return _managed_user(user)


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
