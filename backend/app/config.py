import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    database_url: str
    jwt_secret: str
    app_env: str = "development"
    access_token_minutes: int = 60
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)

    @classmethod
    def from_env(cls):
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        secret = os.getenv("JWT_SECRET", "")
        if len(secret) < 32 or secret.startswith("replace-with-"):
            raise RuntimeError("請先執行 backend/run.ps1，或在 .env 設定至少 32 字元的隨機 JWT_SECRET。")
        environment = os.getenv("APP_ENV", "development")
        url = os.getenv("DATABASE_URL", "sqlite:///./demo.db")
        if environment != "development" and url.startswith("sqlite"):
            raise RuntimeError("SQLite 僅供本機示範；非 development 環境請設定 MySQL。")
        minutes = int(os.getenv("ACCESS_TOKEN_MINUTES", "60"))
        if minutes <= 0:
            raise RuntimeError("ACCESS_TOKEN_MINUTES 必須大於 0。")
        return cls(url, secret, environment, minutes,
                   tuple(x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if x.strip()))
