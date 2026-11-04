from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal
from io import BytesIO

import jwt
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from . import services
from .config import Settings
from .database import Base, build_database, schema_is_current
from .models import BackupRecord, EmailAttempt, Event, EventType, OutgoingEmail, RevokedToken, Unit, User
from .schemas import (AcknowledgeRequest, CancelEventRequest, DocumentRequest, EmailRequest, EventTypeRequest,
                      EventUpdate, ResetPasswordRequest, SignupRequest, TokenRequest, UnitRequest)
from .schemas import (CancellationResponse, EventCreate, EventResponse, EventTypeResponse, LoginRequest,
                      MyEventResponse, RegistrationResponse, TokenResponse, UserResponse)
from .security import decode_token, dummy_hash, issue_token, verify_password
from .services import (cancel_registration, create_event, event_view, get_public_event, list_events,
                       list_my_upcoming_events, register, user_view)

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
        if (user is None or not user.is_active or not user.email_verified or
                claims.get("ver", 0) != user.token_version or db.get(RevokedToken, claims["jti"]) is not None):
            raise HTTPException(401, INVALID_TOKEN, headers={"WWW-Authenticate": "Bearer"})
        request.state.token_claims = claims
        return user


def required_user(user=Depends(optional_user)):
    if user is None:
        raise HTTPException(401, {"code": "AUTH_REQUIRED", "message": "請先登入"}, headers={"WWW-Authenticate": "Bearer"})
    return user


def required_admin(user=Depends(required_user)):
    if user.role != "admin":
        raise HTTPException(403, {"code": "ADMIN_REQUIRED", "message": "權限不足"})
    return user


def create_app(settings=None):
    settings = settings or Settings.from_env()
    engine, sessions = build_database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        if not schema_is_current(engine):
            engine.dispose()
            raise RuntimeError("資料庫結構仍為舊版；請改用全新的 R2 測試資料庫，或由資料庫負責人更新結構。未自動修改原資料。")
        if settings.app_env == "development":
            Base.metadata.create_all(engine)
        yield
        engine.dispose()

    app = FastAPI(title="海大活動報名系統 API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessions = sessions
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_credentials=False, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["Authorization", "Content-Type"])

    @app.middleware("http")
    async def private_response_headers(request, call_next):
        response = await call_next(request)
        if request.headers.get("Authorization") or request.url.path.startswith(("/auth/", "/me/", "/admin/", "/manage/")):
            response.headers["Cache-Control"] = "no-store"
        return response

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
            raise HTTPException(403, {"code": "EMAIL_NOT_VERIFIED", "message": "請先完成信箱驗證"})
        response.headers["Cache-Control"] = "no-store"
        return dict(access_token=issue_token(user.id, request.app.state.settings, user.token_version),
                    token_type="bearer", expires_in=settings.access_token_minutes * 60, user=user_view(db, user))

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

    @app.get("/me/events", response_model=list[MyEventResponse], tags=["個人活動"])
    def my_events(db=Depends(get_db), user=Depends(required_user)):
        return list_my_upcoming_events(db, user)

    @app.delete("/events/{event_id}/registrations/me", response_model=CancellationResponse, tags=["報名"])
    def cancel(event_id: int, request: Request, user=Depends(required_user)):
        return cancel_registration(request.app.state.sessions, event_id, user.id)

    @app.get("/event-types", response_model=list[EventTypeResponse], tags=["活動"])
    def event_types(db=Depends(get_db)):
        return services.list_event_types(db)

    @app.post("/events", response_model=EventResponse, status_code=201, tags=["活動"])
    def create(payload: EventCreate, db=Depends(get_db), user=Depends(required_user)):
        return event_view(db, create_event(db, payload, user.id), user)

    @app.get("/events", response_model=list[EventResponse], tags=["活動"])
    def events(q: str | None = Query(default=None, max_length=200), type: str | None = Query(default=None, max_length=100),
               date_from: date | None = None, date_to: date | None = None,
               db=Depends(get_db), user=Depends(optional_user)):
        if date_from and date_to and date_from > date_to:
            raise HTTPException(422, {"code": "DATE_RANGE_INVALID", "message": "開始日期不得晚於結束日期"})
        if date_to == date.max:
            raise HTTPException(422, {"code": "DATE_RANGE_INVALID", "message": "結束日期超出範圍"})
        result = list_events(db, user, q.strip() if q else None, type, date_from, date_to)
        # All fields are plain response data now. Release the read connection
        # before serializing large lists instead of holding the pool slot.
        db.close()
        return result

    @app.get("/events/{event_id}", response_model=EventResponse, tags=["活動"])
    def detail(event_id: int, db=Depends(get_db), user=Depends(optional_user)):
        return event_view(db, get_public_event(db, event_id), user)

    @app.post("/events/{event_id}/registrations", response_model=RegistrationResponse, tags=["報名"])
    def registration(event_id: int, request: Request, response: Response, user=Depends(required_user)):
        result = register(request.app.state.sessions, event_id, user.id)
        response.status_code = 200 if result["already_registered"] else 201
        return result

    @app.get("/privacy-notice", tags=["文件"])
    def privacy(db=Depends(get_db)):
        return services.document_view(services.current_document(db, "privacy"))

    @app.get("/organizer-terms", tags=["文件"])
    def organizer_terms(db=Depends(get_db)):
        return services.document_view(services.current_document(db, "organizer"))

    @app.get("/faq", tags=["文件"])
    def faq(db=Depends(get_db)):
        return services.document_view(services.current_document(db, "faq"))

    @app.post("/organizer-terms/acknowledgements", tags=["文件"])
    def acknowledge(payload: AcknowledgeRequest, db=Depends(get_db), user=Depends(required_user)):
        return services.acknowledge_organizer(db, user.id, payload.document_id)

    @app.post("/auth/register", status_code=201, tags=["帳號"])
    def signup(payload: SignupRequest, db=Depends(get_db)):
        return services.signup(db, payload, settings)

    @app.post("/auth/verify-email", tags=["帳號"])
    def verify_email(payload: TokenRequest, db=Depends(get_db)):
        return services.consume_account_token(db, payload.token, "verify")

    @app.post("/auth/resend-verification", status_code=202, tags=["帳號"])
    def resend(payload: EmailRequest, db=Depends(get_db)):
        return services.request_account_email(db, payload.email, "verify", settings)

    @app.post("/auth/forgot-password", status_code=202, tags=["帳號"])
    def forgot_password(payload: EmailRequest, db=Depends(get_db)):
        return services.request_account_email(db, payload.email, "reset", settings)

    @app.post("/auth/reset-password", tags=["帳號"])
    def reset_password(payload: ResetPasswordRequest, db=Depends(get_db)):
        return services.consume_account_token(db, payload.token, "reset", payload.password)

    @app.get("/departments", tags=["單位"])
    def departments(db=Depends(get_db)):
        return [dict(id=unit.id, name=unit.name) for unit in db.scalars(
            select(Unit).where(Unit.kind == "department", Unit.is_active.is_(True)).order_by(Unit.name, Unit.id))]

    @app.get("/me/events/history", tags=["個人活動"])
    def history(db=Depends(get_db), user=Depends(required_user)):
        return services.list_my_history(db, user)

    @app.get("/manage/events", tags=["活動管理"])
    def manage_events(db=Depends(get_db), user=Depends(required_user)):
        return services.manage_events(db, user)

    @app.get("/events/{event_id}/registrations", tags=["活動管理"])
    def roster(event_id: int, db=Depends(get_db), user=Depends(required_user)):
        return services.registration_roster(db, event_id, user.id)

    @app.patch("/events/{event_id}", response_model=EventResponse, tags=["活動管理"])
    def edit(event_id: int, payload: EventUpdate, db=Depends(get_db), user=Depends(required_user)):
        return services.edit_event(db, event_id, user.id, payload)

    @app.post("/events/{event_id}/cancel", response_model=EventResponse, tags=["活動管理"])
    def cancel_event(event_id: int, payload: CancelEventRequest, db=Depends(get_db), user=Depends(required_user)):
        return services.cancel_event(db, event_id, user.id, payload.reason)

    @app.get("/events/{event_id}/qr", tags=["活動管理"])
    def poster_qr(event_id: int, db=Depends(get_db), user=Depends(required_user)):
        import qrcode
        services.managed_event(db, event_id, user.id)
        image = qrcode.make(f"{settings.public_base_url}/events/{event_id}")
        stream = BytesIO()
        image.save(stream, format="PNG")
        return Response(stream.getvalue(), media_type="image/png",
                        headers={"Content-Disposition": f'attachment; filename="event-{event_id}.png"'})

    @app.get("/admin/users", tags=["系統管理"])
    def search_users(q: str | None = Query(default=None, max_length=200), unit_id: int | None = Query(default=None, gt=0),
                     role: Literal["member", "manager", "admin"] | None = None,
                     page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
                     db=Depends(get_db), user=Depends(required_admin)):
        return services.search_users(db, q, unit_id, role, page, page_size)

    @app.put("/admin/units/{unit_id}/managers/{user_id}", tags=["系統管理"])
    def assign(unit_id: int, user_id: int, db=Depends(get_db), admin=Depends(required_admin)):
        return services.change_unit_manager(db, user_id, unit_id, True)

    @app.delete("/admin/units/{unit_id}/managers/{user_id}", tags=["系統管理"])
    def revoke(unit_id: int, user_id: int, db=Depends(get_db), admin=Depends(required_admin)):
        return services.change_unit_manager(db, user_id, unit_id, False)

    @app.get("/admin/units", tags=["系統管理"])
    def units(db=Depends(get_db), admin=Depends(required_admin)):
        return [dict(id=x.id, name=x.name, kind=x.kind, is_active=x.is_active) for x in db.scalars(select(Unit).order_by(Unit.id))]

    @app.post("/admin/units", status_code=201, tags=["系統管理"])
    def create_unit(payload: UnitRequest, db=Depends(get_db), admin=Depends(required_admin)):
        return services.maintain_unit(db, payload)

    @app.put("/admin/units/{unit_id}", tags=["系統管理"])
    def update_unit(unit_id: int, payload: UnitRequest, db=Depends(get_db), admin=Depends(required_admin)):
        return services.maintain_unit(db, payload, unit_id)

    @app.delete("/admin/units/{unit_id}", tags=["系統管理"])
    def delete_unit(unit_id: int, db=Depends(get_db), admin=Depends(required_admin)):
        return services.maintain_unit(db, None, unit_id, delete=True)

    @app.get("/admin/event-types", tags=["系統管理"])
    def all_event_types(db=Depends(get_db), admin=Depends(required_admin)):
        return [dict(id=x.id, name=x.name, is_active=x.is_active) for x in db.scalars(select(EventType).order_by(EventType.id))]

    @app.post("/admin/event-types", status_code=201, tags=["系統管理"])
    def create_type(payload: EventTypeRequest, db=Depends(get_db), admin=Depends(required_admin)):
        return services.maintain_event_type(db, payload)

    @app.put("/admin/event-types/{type_id}", tags=["系統管理"])
    def update_type(type_id: int, payload: EventTypeRequest, db=Depends(get_db), admin=Depends(required_admin)):
        return services.maintain_event_type(db, payload, type_id)

    @app.delete("/admin/event-types/{type_id}", tags=["系統管理"])
    def delete_type(type_id: int, db=Depends(get_db), admin=Depends(required_admin)):
        return services.maintain_event_type(db, None, type_id, delete=True)

    @app.post("/admin/documents/{kind}", status_code=201, tags=["系統管理"])
    def publish(kind: Literal["privacy", "organizer", "faq"], payload: DocumentRequest,
                db=Depends(get_db), admin=Depends(required_admin)):
        db.scalar(select(User).where(User.id == admin.id).with_for_update())
        return services.publish_document(db, kind, payload.content)

    @app.get("/admin/emails", tags=["維運"])
    def emails(status: Literal["pending", "sending", "sent", "failed"] | None = None,
               page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
               db=Depends(get_db), admin=Depends(required_admin)):
        query = select(OutgoingEmail).order_by(OutgoingEmail.id.desc())
        if status:
            query = query.where(OutgoingEmail.status == status)
        return [dict(id=x.id, recipient=x.recipient, subject=x.subject, status=x.status, attempts=x.attempts,
                     created_at=services.as_utc(x.created_at), sent_at=services.as_utc(x.sent_at) if x.sent_at else None,
                     failures=[dict(at=services.as_utc(a.attempted_at), error=a.error) for a in db.scalars(
                         select(EmailAttempt).where(EmailAttempt.email_id == x.id, EmailAttempt.error.is_not(None)).order_by(EmailAttempt.id))])
                for x in db.scalars(query.offset((page - 1) * page_size).limit(page_size))]

    @app.post("/admin/emails/{email_id}/retry", status_code=202, tags=["維運"])
    def retry_email(email_id: int, db=Depends(get_db), admin=Depends(required_admin)):
        email = db.scalar(select(OutgoingEmail).where(OutgoingEmail.id == email_id).with_for_update())
        if email is None:
            services.fail(404, "EMAIL_NOT_FOUND", "找不到寄信紀錄")
        if email.status != "failed":
            services.fail(409, "EMAIL_NOT_FAILED", "只有寄送失敗的信件可以手動重寄")
        email.status, email.attempts, email.next_attempt_at = "pending", 0, services.utc_now()
        db.commit()
        return dict(id=email.id, status="pending")

    @app.get("/admin/backups", tags=["維運"])
    def backups(db=Depends(get_db), admin=Depends(required_admin)):
        return [dict(id=x.id, created_at=services.as_utc(x.created_at), status=x.status, filename=x.filename, error=x.error)
                for x in db.scalars(select(BackupRecord).where(BackupRecord.created_at >= services.utc_now() - timedelta(days=7))
                                    .order_by(BackupRecord.created_at.desc()))]

    return app
