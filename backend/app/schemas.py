from datetime import datetime
import re
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, model_validator


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
    waitlist_enabled: bool = Field(default=False, strict=True)
    waitlist_capacity: int | None = Field(default=None, strict=True, gt=0)
    eligibility_identities: list[Literal["student", "teacher", "staff"]] = Field(default_factory=list)
    eligibility_department_ids: list[StrictInt] = Field(default_factory=list, max_length=500)
    eligibility_grades: list[StrictInt] = Field(default_factory=list, max_length=100)
    confirm_overlap: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def validate_times(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be later than start_time")
        if self.registration_start >= self.registration_deadline:
            raise ValueError("registration_start must be earlier than registration_deadline")
        if self.registration_deadline > self.start_time:
            raise ValueError("registration_deadline must not be later than start_time")
        if self.waitlist_enabled and self.capacity is None:
            raise ValueError("unlimited capacity cannot enable waitlist")
        if self.waitlist_enabled and self.waitlist_capacity is None:
            self.waitlist_capacity = (self.capacity + 1) // 2
        if not self.waitlist_enabled and self.waitlist_capacity is not None:
            raise ValueError("waitlist_capacity requires waitlist_enabled")
        if any(type(x) is not int or x <= 0 for x in self.eligibility_department_ids):
            raise ValueError("eligibility_department_ids must be positive integers")
        if any(x <= 0 for x in self.eligibility_grades):
            raise ValueError("eligibility_grades must be positive integers")
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
    waitlist_enabled: bool = False
    waitlist_capacity: int | None = None
    eligibility_identities: list[str] = Field(default_factory=list)
    eligibility_department_ids: list[int] = Field(default_factory=list)
    eligibility_grades: list[int] = Field(default_factory=list)
    eligibility_description: str = "不限"
    waitlist_position: int | None = None
    cancellation_request: dict | None = None
    can_cancel_registration: bool = False
    direct_cancel_deadline: datetime | None = None
    can_request_cancellation: bool = False


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
    waitlist_position: int | None = None
    waitlist_count: int = 0
    waitlist_enabled: bool = False


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
    status: Literal["registered", "waitlisted"] = "registered"
    registered_at: datetime
    registration_status: str = "已報名"
    registered_count: int
    registration_count: int
    capacity: int | None
    already_registered: bool
    waitlist_position: int | None = None
    waitlist_count: int = 0


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
    waitlist_enabled: bool | None = Field(default=None, strict=True)
    waitlist_capacity: int | None = Field(default=None, strict=True, gt=0)
    eligibility_identities: list[Literal["student", "teacher", "staff"]] | None = None
    eligibility_department_ids: list[StrictInt] | None = Field(default=None, max_length=500)
    eligibility_grades: list[StrictInt] | None = Field(default=None, max_length=100)
    confirm_overlap: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def no_null_required_fields(self):
        for key in self.model_fields_set - {"capacity", "notes", "waitlist_capacity"}:
            if getattr(self, key) is None:
                raise ValueError(f"{key} cannot be null")
        return self


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    department_id: int = Field(strict=True, gt=0)
    grade: int | None = Field(default=None, strict=True, ge=1)


class IdentityUpdate(ProfileUpdate):
    identity: Literal["student", "teacher", "staff"]


class RegistrationSwitch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_event_ids: list[StrictInt] = Field(min_length=1, max_length=100)
    source_status: Literal["registered", "waitlisted"]
    confirmed: Literal[True]

    @model_validator(mode="after")
    def positive_sources(self):
        if any(x <= 0 for x in self.source_event_ids):
            raise ValueError("source_event_ids must be positive")
        return self


class ConfirmedReason(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=1, max_length=2000)
    confirmed: Literal[True]


class CancellationReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    decision: Literal["approve", "reject"]
    reason: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def rejection_needs_reason(self):
        if self.decision == "reject" and not self.reason:
            raise ValueError("rejection requires reason")
        return self


class AttendanceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["present", "absent"]


class CancellationActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=1, max_length=2048)


class CancelEventRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def not_blank(self):
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("reason cannot be blank")
        return self
