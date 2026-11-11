from datetime import datetime
import re
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class UnitResponse(BaseModel):
    id: int
    name: str


class EventTypeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str
    identity: str | None = None
    department: UnitResponse | None = None
    grade: int | None = None
    managed_units: list[UnitResponse]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class EventCreate(BaseModel):
    # Reject owner_id and all other undeclared fields; the server sets creator.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    type: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1)
    location: str = Field(min_length=1, max_length=255)
    contact_information: str = Field(min_length=1, max_length=255)
    start_time: AwareDatetime
    end_time: AwareDatetime
    registration_start: AwareDatetime
    registration_deadline: AwareDatetime
    capacity: int | None = Field(default=None, strict=True, gt=0)
    unit_id: int = Field(strict=True, gt=0)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_times(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be later than start_time")
        if self.registration_start >= self.registration_deadline:
            raise ValueError("registration_start must be earlier than registration_deadline")
        if self.registration_deadline > self.start_time:
            raise ValueError("registration_deadline must not be later than start_time")
        return self


class EventResponse(BaseModel):
    id: int
    name: str
    type: str
    unit_id: int
    unit: UnitResponse
    contact_information: str
    start_time: datetime
    end_time: datetime
    registration_start: datetime
    registration_deadline: datetime
    registration_count: int
    # Legacy response names kept during team integration; use names above for new clients.
    category: str
    location: str
    description: str
    notes: str | None
    starts_at: datetime
    ends_at: datetime
    registration_opens_at: datetime
    registration_closes_at: datetime
    capacity: int | None
    registered_count: int
    waitlist_count: int = 0
    status: Literal["報名未開始", "開放中", "已額滿", "已截止", "進行中", "已結束", "已取消"]
    my_registration_status: str | None
    can_register: bool
    cancellation_reason: str | None = None


class EventSummary(BaseModel):
    """Home-page list item: only what a card shows, to keep GET /events small (NFR-01-02)."""
    id: int
    name: str
    type: str
    unit: UnitResponse
    location: str
    start_time: datetime
    end_time: datetime
    registration_count: int
    capacity: int | None
    status: Literal["報名未開始", "開放中", "已額滿", "已截止", "進行中", "已結束", "已取消"]
    my_registration_status: str | None


class MyEventResponse(EventResponse):
    registration_id: int
    registered_at: datetime
    can_cancel_registration: bool


class CancellationResponse(BaseModel):
    message: str = "已取消報名"
    registration_id: int
    event_id: int
    status: Literal["cancelled"] = "cancelled"
    registration_count: int
    capacity: int | None


class RegistrationResponse(BaseModel):
    message: str
    registration_id: int
    event_id: int
    status: Literal["registered"] = "registered"
    registered_at: datetime
    registration_status: str = "已報名"
    registered_count: int
    registration_count: int
    capacity: int | None
    already_registered: bool


class EmailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)

    @model_validator(mode="after")
    def normalize_email(self):
        self.email = self.email.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", self.email):
            raise ValueError("invalid email")
        return self


class PasswordRequest(BaseModel):
    password: str = Field(min_length=8, max_length=256)

    @model_validator(mode="after")
    def password_rule(self):
        if not re.search(r"[A-Za-z]", self.password) or not re.search(r"[0-9]", self.password):
            raise ValueError("password must contain letters and digits")
        return self


class SignupRequest(EmailRequest, PasswordRequest):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    identity: Literal["student", "teacher", "staff"]
    department_id: int = Field(strict=True, gt=0)
    grade: int | None = Field(default=None, strict=True, gt=0)
    consent: bool
    privacy_version: int = Field(strict=True, gt=0)

    @model_validator(mode="after")
    def profile_rule(self):
        self.name = self.name.strip()
        if not self.name or (self.identity == "student" and self.grade is None):
            raise ValueError("name and student grade are required")
        return self


class TokenRequest(BaseModel):
    token: str = Field(min_length=16, max_length=256)


class ResetPasswordRequest(TokenRequest, PasswordRequest):
    pass


class DocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    content: str = Field(min_length=1, max_length=100000)


class AcknowledgeRequest(BaseModel):
    document_id: int = Field(strict=True, gt=0)


class UnitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["department", "office", "club"]
    is_active: bool = True


class EventTypeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    is_active: bool = True


class EventUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, min_length=1)
    location: str | None = Field(default=None, min_length=1, max_length=255)
    contact_information: str | None = Field(default=None, min_length=1, max_length=255)
    start_time: AwareDatetime | None = None
    end_time: AwareDatetime | None = None
    registration_start: AwareDatetime | None = None
    registration_deadline: AwareDatetime | None = None
    capacity: int | None = Field(default=None, strict=True, gt=0)
    notes: str | None = None

    @model_validator(mode="after")
    def no_null_required_fields(self):
        for key in self.model_fields_set - {"capacity", "notes"}:
            if getattr(self, key) is None:
                raise ValueError(f"{key} cannot be null")
        return self


class CancelEventRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def not_blank(self):
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("reason cannot be blank")
        return self
