from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class UnitResponse(BaseModel):
    id: int
    name: str


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str
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
