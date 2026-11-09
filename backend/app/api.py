from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta, date
from typing import Annotated
import hashlib
import secrets
import re

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, update

from . import services
from .config import Settings
from .database import Base, build_database
from .models import RevokedToken, User, Unit, EmailVerificationToken, PasswordResetToken
from .schemas import (EventCreate, EventResponse, EventTypeResponse, LoginRequest, RegistrationResponse,
                      TokenResponse, UserResponse, RegisterRequest, PasswordResetRequest, PasswordResetConfirm, TokenRequest)
from .security import decode_token, dummy_hash, issue_token, verify_password, hash_password
from .mailer import send_link
from .services import create_event, event_view, get_public_event, list_events, register, user_view

bearer = HTTPBearer(auto_error=False)
INVALID_TOKEN = {"code": "INVALID_TOKEN", "message": "登入已失效，請重新登入"}


def get_db(request: Request):
    with request.app.state.sessions() as db:
        yield db


def optional_user(request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if credentials is None:
        return None
    try:
        claims = decode_token(credentials.credentials, request.app.state.settings)
        user_id = int(claims["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise HTTPException(401, INVALID_TOKEN, headers={"WWW-Authenticate": "Bearer"})
    # Release the authentication connection before the registration transaction.
    # Otherwise many requests could hold all pool connections while waiting for
    # a second connection to register, leaving no request able to finish.
    with request.app.state.sessions() as db:
        user = db.get(User, user_id)
        if user is None or not user.is_active or claims.get("ver", 0) != user.token_version or db.get(RevokedToken, claims["jti"]) is not None:
            raise HTTPException(401, INVALID_TOKEN, headers={"WWW-Authenticate": "Bearer"})
        request.state.token_claims = claims
        return user


def required_user(user=Depends(optional_user)):
    if user is None:
        raise HTTPException(401, {"code": "AUTH_REQUIRED", "message": "請先登入"}, headers={"WWW-Authenticate": "Bearer"})
    return user


def create_app(settings=None):
    settings = settings or Settings.from_env()
    engine, sessions = build_database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        if settings.app_env == "development":
            Base.metadata.create_all(engine)
        yield
        engine.dispose()

    app = FastAPI(title="海大活動報名系統 API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessions = sessions
    app.state.email_outbox = []
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_credentials=False, allow_methods=["GET", "POST"],
                       allow_headers=["Authorization", "Content-Type"])

    @app.get("/")
    def read_root():
        return {"message": "歡迎來到海大活動報名系統 API"}

    @app.post("/auth/login", response_model=TokenResponse, tags=["登入"])
    def login(payload: LoginRequest, request: Request, response: Response, db=Depends(get_db)):
        email = payload.email.strip().lower()
        now = services.utc_now()
        # Locked emails are refused even with the right password (NFR-05-04).
        # Unregistered emails are counted too, so the reply reveals nothing.
        minutes = services.lockout_remaining(db, email, now)
        if minutes is not None:
            raise HTTPException(429, {"code": "LOGIN_LOCKED", "message": f"登入失敗次數過多，請於 {minutes} 分鐘後再試",
                                      "retry_after_minutes": minutes})
        user = db.scalar(select(User).where(User.email == email))
        valid = verify_password(payload.password, user.password_hash if user else dummy_hash)
        success = valid and user is not None and user.is_active
        services.record_login_result(db, email, success, now)
        if not success:
            raise HTTPException(401, {"code": "INVALID_CREDENTIALS", "message": "帳號或密碼錯誤"})
        if not user.email_verified:
            raise HTTPException(403, {"code": "EMAIL_NOT_VERIFIED", "message": "請先完成學校信箱驗證"})
        response.headers["Cache-Control"] = "no-store"
        return dict(access_token=issue_token(user.id, request.app.state.settings, user.token_version),
                    token_type="bearer", expires_in=settings.access_token_minutes * 60, user=user_view(db, user))

    def token_digest(raw):
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def create_verification(db, request, user):
        # Replacing the outstanding token makes every previously mailed link unusable.
        db.query(EmailVerificationToken).filter(EmailVerificationToken.user_id == user.id,
                                                EmailVerificationToken.used_at.is_(None)).delete()
        raw = secrets.token_urlsafe(32)
        now = services.utc_now()
        db.add(EmailVerificationToken(user_id=user.id, token_hash=token_digest(raw),
                                      expires_at=now + timedelta(hours=24)))
        user.verification_sent_at = now
        db.commit()
        link = f"{settings.frontend_url}/verify-email?token={raw}"
        send_link(settings, app.state.email_outbox, user.email, "海大活動報名系統－信箱驗證",
                  f"請在 24 小時內開啟以下連結完成信箱驗證：\\n{link}")

    def create_password_reset(db, user):
        db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user.id,
                                             PasswordResetToken.used_at.is_(None)).delete()
        raw = secrets.token_urlsafe(32)
        db.add(PasswordResetToken(user_id=user.id, token_hash=token_digest(raw),
                                  expires_at=services.utc_now() + timedelta(hours=1)))
        db.commit()
        link = f"{settings.frontend_url}/reset-password?token={raw}"
        send_link(settings, app.state.email_outbox, user.email, "海大活動報名系統－重設密碼",
                  f"請在 1 小時內使用以下連結重設密碼（僅能使用一次）：\\n{link}")

    @app.get("/units", tags=["註冊"])
    def units(db=Depends(get_db)):
        return [dict(id=item.id, name=item.name) for item in
                db.scalars(select(Unit).where(Unit.kind == "department").order_by(Unit.name)).all()]

    @app.post("/auth/register", status_code=201, tags=["註冊"])
    def register_account(payload: RegisterRequest, request: Request, db=Depends(get_db)):
        email = payload.email.strip().lower()
        domain = email.rsplit("@", 1)[-1] if "@" in email else ""
        if not re.fullmatch(r"[^\s@]+@[^\s@]+", email) or domain not in settings.school_email_domains:
            raise HTTPException(422, {"code": "SCHOOL_EMAIL_REQUIRED", "message": "請使用學校核發的信箱註冊"})
        if db.scalar(select(User).where(User.email == email)):
            raise HTTPException(409, {"code": "EMAIL_EXISTS", "message": "此信箱已被使用"})
        unit = db.get(Unit, payload.department_id)
        if unit is None or unit.kind != "department":
            raise HTTPException(422, {"code": "DEPARTMENT_INVALID", "message": "請從系所清單選擇"})
        user = User(email=email, name=payload.name, identity=payload.identity,
                    department_id=unit.id, grade=payload.grade,
                    password_hash=hash_password(payload.password), role="member",
                    is_active=True, email_verified=False, token_version=0)
        db.add(user)
        db.flush()
        create_verification(db, request, user)
        return {"message": "註冊成功，請至學校信箱完成驗證後再登入"}

    @app.post("/auth/verify-email", tags=["註冊"])
    def verify_email(payload: TokenRequest, db=Depends(get_db)):
        record = db.scalar(select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == token_digest(payload.token)).with_for_update())
        now = services.utc_now()
        if record is None or record.used_at is not None or now >= record.expires_at:
            raise HTTPException(400, {"code": "VERIFICATION_INVALID", "message": "驗證連結無效或已過期"})
        claimed = db.execute(update(EmailVerificationToken).where(
            EmailVerificationToken.id == record.id,
            EmailVerificationToken.used_at.is_(None),
            EmailVerificationToken.expires_at > now).values(used_at=now))
        if claimed.rowcount != 1:
            raise HTTPException(400, {"code": "VERIFICATION_INVALID", "message": "驗證連結無效或已過期"})
        user = db.get(User, record.user_id)
        if user is None:
            raise HTTPException(400, {"code": "VERIFICATION_INVALID", "message": "驗證連結無效或已過期"})
        user.email_verified = True
        db.commit()
        return {"message": "信箱驗證成功，現在可以登入"}

    @app.post("/auth/resend-verification", tags=["註冊"])
    def resend_verification(payload: PasswordResetRequest, request: Request, db=Depends(get_db)):
        email = payload.email.strip().lower()
        user = db.scalar(select(User).where(User.email == email))
        now = services.utc_now()
        if user is not None and not user.email_verified:
            if user.verification_sent_at and now < user.verification_sent_at + timedelta(seconds=60):
                wait = max(1, int((user.verification_sent_at + timedelta(seconds=60) - now).total_seconds()))
                raise HTTPException(429, {"code": "RESEND_TOO_SOON", "message": f"請等待 {wait} 秒後再重新寄送"})
            create_verification(db, request, user)
        return {"message": "若此信箱有尚未驗證的帳號，系統將寄送驗證信"}

    @app.post("/auth/password-reset/request", tags=["密碼重設"])
    def request_password_reset(payload: PasswordResetRequest, db=Depends(get_db)):
        user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
        if user is not None and user.email_verified:
            create_password_reset(db, user)
        return {"message": "若此信箱已註冊，系統將寄送密碼重設連結"}

    @app.post("/auth/password-reset/confirm", tags=["密碼重設"])
    def confirm_password_reset(payload: PasswordResetConfirm, db=Depends(get_db)):
        record = db.scalar(select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_digest(payload.token)).with_for_update())
        now = services.utc_now()
        if record is None or record.used_at is not None or now >= record.expires_at:
            raise HTTPException(400, {"code": "RESET_TOKEN_INVALID", "message": "重設連結無效、已使用或已過期"})
        user = db.get(User, record.user_id)
        if user is None:
            raise HTTPException(400, {"code": "RESET_TOKEN_INVALID", "message": "重設連結無效、已使用或已過期"})
        claimed = db.execute(update(PasswordResetToken).where(
            PasswordResetToken.id == record.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now).values(used_at=now))
        if claimed.rowcount != 1:
            raise HTTPException(400, {"code": "RESET_TOKEN_INVALID", "message": "重設連結無效、已使用或已過期"})
        user.password_hash = hash_password(payload.password)
        user.token_version += 1
        db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user.id,
                                            PasswordResetToken.used_at.is_(None)).update({"used_at": now})
        db.commit()
        return {"message": "密碼重設成功，請使用新密碼重新登入"}

    @app.post("/auth/logout", status_code=204, tags=["登入"])
    def logout(request: Request, db=Depends(get_db), user=Depends(required_user)):
        # Revoke this token server-side so a copied token stops working (ER-US-A05).
        claims = request.state.token_claims
        if db.get(RevokedToken, claims["jti"]) is None:
            db.add(RevokedToken(jti=claims["jti"],
                                expires_at=datetime.fromtimestamp(claims["exp"], timezone.utc).replace(tzinfo=None)))
            db.commit()
        return Response(status_code=204)

    @app.get("/auth/me", response_model=UserResponse, tags=["登入"])
    def me(db=Depends(get_db), user=Depends(required_user)):
        return user_view(db, user)

    @app.get("/event-types", response_model=list[EventTypeResponse], tags=["活動"])
    def event_types(db=Depends(get_db)):
        return services.list_event_types(db)

    @app.post("/events", response_model=EventResponse, status_code=201, tags=["活動"])
    def create(payload: EventCreate, db=Depends(get_db), user=Depends(required_user)):
        return event_view(db, create_event(db, payload, user.id), user)

    @app.get("/events", response_model=list[EventResponse], tags=["活動"])
    def events(q: str | None = Query(default=None, max_length=200),
               event_type: str | None = Query(default=None, alias="type", max_length=100),
               date_from: date | None = None, date_to: date | None = None,
               db=Depends(get_db), user=Depends(optional_user)):
        if date_from and date_to and date_from > date_to:
            raise HTTPException(422, {"code": "INVALID_DATE_RANGE", "message": "結束日期不可早於開始日期"})
        return list_events(db, user, q, event_type, date_from, date_to)

    @app.get("/events/{event_id}", response_model=EventResponse, tags=["活動"])
    def detail(event_id: int, db=Depends(get_db), user=Depends(optional_user)):
        return event_view(db, get_public_event(db, event_id), user)

    @app.post("/events/{event_id}/registrations", response_model=RegistrationResponse, tags=["報名"])
    def registration(event_id: int, request: Request, response: Response, user=Depends(required_user)):
        result = register(request.app.state.sessions, event_id, user.id)
        response.status_code = 200 if result["already_registered"] else 201
        return result

    return app
