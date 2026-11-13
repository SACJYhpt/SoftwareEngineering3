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
    school_domains: tuple[str, ...] = ("ntou.edu.tw",)
    public_base_url: str = "http://localhost:5173"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_security: str = "starttls"
    mail_from: str = "events@ntou.edu.tw"
    backup_dir: str = str(Path(__file__).resolve().parents[1] / ".backups")
    backup_enabled: bool = False

    @classmethod
    def from_env(cls):
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        secret = os.getenv("JWT_SECRET", "")
        if len(secret) < 32 or secret.startswith("replace-with-"):
            raise RuntimeError("請先執行 backend/run.ps1，或在 .env 設定至少 32 字元的隨機 JWT_SECRET。")
        environment = os.getenv("APP_ENV", "development")
        url = os.getenv("DATABASE_URL", "sqlite:///./demo.db")
        # A relative SQLite path means "inside backend/", wherever the process was started.
        if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
            path = Path(url[len("sqlite:///"):])
            if not path.is_absolute():
                url = "sqlite:///" + (Path(__file__).resolve().parents[1] / path).resolve().as_posix()
        if environment != "development" and url.startswith("sqlite"):
            raise RuntimeError("SQLite 僅供本機示範；非 development 環境請設定 MySQL。")
        minutes = int(os.getenv("ACCESS_TOKEN_MINUTES", "60"))
        if minutes <= 0:
            raise RuntimeError("ACCESS_TOKEN_MINUTES 必須大於 0。")
        base_url = os.getenv("PUBLIC_BASE_URL", "http://localhost:5173").rstrip("/")
        from urllib.parse import urlsplit
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment or parsed.username:
            raise RuntimeError("PUBLIC_BASE_URL 必須是完整的網站網址，不可含憑證、query 或 fragment。")
        security = os.getenv("SMTP_SECURITY", "starttls")
        if security not in {"starttls", "ssl", "none"}:
            raise RuntimeError("SMTP_SECURITY 必須是 starttls、ssl 或 none。")
        return cls(url, secret, environment, minutes,
                   tuple(x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if x.strip()),
                   tuple(x.strip().lower() for x in os.getenv("SCHOOL_EMAIL_DOMAINS", "ntou.edu.tw").split(",") if x.strip()),
                   base_url, os.getenv("SMTP_HOST", ""), int(os.getenv("SMTP_PORT", "587")),
                   os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASSWORD", ""), security,
                   os.getenv("MAIL_FROM", "events@ntou.edu.tw"),
                   os.getenv("BACKUP_DIR", cls.backup_dir), os.getenv("BACKUP_ENABLED", "0") == "1")
