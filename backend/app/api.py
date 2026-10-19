from contextlib import asynccontextmanager
from typing import Annotated

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from .config import Settings
from .database import Base, build_database
from .models import User
from .schemas import EventCreate, EventResponse, LoginRequest, RegistrationResponse, TokenResponse, UserResponse
from .security import decode_token, dummy_hash, issue_token, verify_password
from .services import create_event, event_view, get_public_event, list_events, register, user_view

bearer = HTTPBearer(auto_error=False)


def get_db(request: Request):
    with request.app.state.sessions() as db:
        yield db


def optional_user(request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if credentials is None:
        return None
    try:
        user_id = decode_token(credentials.credentials, request.app.state.settings)
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise HTTPException(401, {"code": "INVALID_TOKEN", "message": "登入已失效，請重新登入"}, headers={"WWW-Authenticate": "Bearer"})
    # Release the authentication connection before the registration transaction.
    # Otherwise many requests could hold all pool connections while waiting for
    # a second connection to register, leaving no request able to finish.
    with request.app.state.sessions() as db:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            raise HTTPException(401, {"code": "INVALID_TOKEN", "message": "登入已失效，請重新登入"}, headers={"WWW-Authenticate": "Bearer"})
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
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_credentials=True, allow_methods=["GET", "POST"],
                       allow_headers=["Authorization", "Content-Type"])

    @app.get("/")
    def read_root():
        return {"message": "歡迎來到海大活動報名系統 API"}

    @app.post("/auth/login", response_model=TokenResponse, tags=["登入"])
    def login(payload: LoginRequest, request: Request, response: Response, db=Depends(get_db)):
        user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
        valid = verify_password(payload.password, user.password_hash if user else dummy_hash)
        if not valid or user is None or not user.is_active:
            raise HTTPException(401, {"code": "INVALID_CREDENTIALS", "message": "帳號或密碼錯誤"})
        response.headers["Cache-Control"] = "no-store"
        return dict(access_token=issue_token(user.id, request.app.state.settings),
                    token_type="bearer", expires_in=settings.access_token_minutes * 60, user=user_view(db, user))

    @app.get("/auth/me", response_model=UserResponse, tags=["登入"])
    def me(db=Depends(get_db), user=Depends(required_user)):
        return user_view(db, user)

    @app.post("/events", response_model=EventResponse, status_code=201, tags=["活動"])
    def create(payload: EventCreate, db=Depends(get_db), user=Depends(required_user)):
        return event_view(db, create_event(db, payload, user.id), user)

    @app.get("/events", response_model=list[EventResponse], tags=["活動"])
    def events(db=Depends(get_db), user=Depends(optional_user)):
        return list_events(db, user)

    @app.get("/events/{event_id}", response_model=EventResponse, tags=["活動"])
    def detail(event_id: int, db=Depends(get_db), user=Depends(optional_user)):
        return event_view(db, get_public_event(db, event_id), user)

    @app.post("/events/{event_id}/registrations", response_model=RegistrationResponse, tags=["報名"])
    def registration(event_id: int, request: Request, response: Response, user=Depends(required_user)):
        result = register(request.app.state.sessions, event_id, user.id)
        response.status_code = 200 if result["already_registered"] else 201
        return result

    return app
