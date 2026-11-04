from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('member', 'manager', 'admin')", name="ck_user_role"),
        CheckConstraint("identity IS NULL OR identity IN ('student', 'teacher', 'staff')", name="ck_user_identity"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="member")
    is_active: Mapped[bool] = mapped_column(default=True)
    # Profile used by registration and eligibility (SRD ER-US-A01). MVP accounts
    # come from init_data.py; self sign-up arrives in R2.
    identity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"), nullable=True)
    grade: Mapped[int | None] = mapped_column(Integer, nullable=True)
    email_verified: Mapped[bool] = mapped_column(default=False, server_default=text("0"))
    token_version: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    consent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    privacy_version: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Unit(Base):
    __tablename__ = "units"
    __table_args__ = (
        CheckConstraint("kind IN ('department', 'office', 'club')", name="ck_unit_kind"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20), default="department")
    is_active: Mapped[bool] = mapped_column(default=True)


class EventType(Base):
    """Event type choices for the create form; maintained by admins in R2 (ER-US-I05)."""
    __tablename__ = "event_types"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    is_active: Mapped[bool] = mapped_column(default=True)


class RevokedToken(Base):
    """Logged-out tokens (ER-US-A05). Rows may be purged once expires_at has passed."""
    __tablename__ = "revoked_tokens"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}
    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class LoginThrottle(Base):
    """Consecutive login failures per normalized email (NFR-05-04).

    Keyed by email rather than user id so unregistered emails are throttled the
    same way and the response does not reveal whether an account exists.
    """
    __tablename__ = "login_throttles"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}
    email: Mapped[str] = mapped_column(String(254), primary_key=True)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UnitManager(Base):
    """SRD v2: grants apply to every event in the unit, not its creator.

    A user may manage multiple units; the association is the permission source.
    User.role alone does not grant access to any unit.
    """
    __tablename__ = "unit_managers"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), primary_key=True, index=True)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("capacity IS NULL OR capacity > 0", name="ck_event_capacity"),
        CheckConstraint("ends_at >= starts_at", name="ck_event_time"),
        CheckConstraint("registration_opens_at <= registration_closes_at", name="ck_registration_time"),
        CheckConstraint("registration_closes_at <= starts_at", name="ck_registration_before_event"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    # SRD v2: unit owns the event; all its assigned managers may manage it.
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    # SRD v2: legacy name retained only as creator history (created_by).
    # Never use owner_id for management authorization.
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(100))
    location: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    contact_information: Mapped[str] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime)
    registration_opens_at: Mapped[datetime] = mapped_column(DateTime)
    registration_closes_at: Mapped[datetime] = mapped_column(DateTime)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_public: Mapped[bool] = mapped_column(default=True)
    is_cancelled: Mapped[bool] = mapped_column(default=False)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class Registration(Base):
    __tablename__ = "registrations"
    __table_args__ = (
        UniqueConstraint("user_id", "event_id", name="uq_registration_user_event"),
        CheckConstraint("status IN ('registered', 'cancelled')", name="ck_registration_status"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="registered", server_default="registered", index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PublishedDocument(Base):
    """Versioned privacy notice, organizer terms, and FAQ; old versions remain immutable."""
    __tablename__ = "published_documents"
    __table_args__ = (UniqueConstraint("kind", "version", name="uq_document_version"),
                     {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"})
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime)


class OrganizerAcknowledgement(Base):
    __tablename__ = "organizer_acknowledgements"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("published_documents.id"), primary_key=True)
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime)


class AccountToken(Base):
    """Only a digest is kept here; plaintext links belong to the private mail outbox."""
    __tablename__ = "account_tokens"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(20))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AccountRequest(Base):
    __tablename__ = "account_requests"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}
    email: Mapped[str] = mapped_column(String(254), primary_key=True)
    purpose: Mapped[str] = mapped_column(String(20), primary_key=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime)


class OutgoingEmail(Base):
    __tablename__ = "outgoing_emails"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}
    id: Mapped[int] = mapped_column(primary_key=True)
    recipient: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class EmailAttempt(Base):
    __tablename__ = "email_attempts"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}
    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("outgoing_emails.id"), index=True)
    attempted_at: Mapped[datetime] = mapped_column(DateTime)
    error: Mapped[str | None] = mapped_column(String(255), nullable=True)


class BackupRecord(Base):
    __tablename__ = "backup_records"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(String(255), nullable=True)
