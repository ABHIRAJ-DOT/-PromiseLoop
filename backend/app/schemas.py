"""Pydantic request/response models."""

import uuid
from datetime import date, datetime, time, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Status = Literal["pending", "in_progress", "completed", "cancelled"]
Priority = Literal["low", "normal", "high"]
Precision = Literal["exact", "day", "vague", "none"]


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; every datetime we store is UTC, so re-attach it."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class CommitmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    recipient: str | None = Field(default=None, max_length=200)
    details: str | None = Field(default=None, max_length=5000)
    status: Status = "pending"
    priority: Priority = "normal"
    due_at: datetime | None = None
    due_local_date: date | None = None
    due_local_time: time | None = None
    deadline_precision: Precision = "none"
    timezone: str = Field(default="UTC", max_length=64)
    source: str = Field(default="manual", max_length=40)
    original_text: str | None = Field(default=None, max_length=10000)
    depends_on_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("due_at")
    @classmethod
    def _due_at_utc(cls, v: datetime | None) -> datetime | None:
        return as_utc(v)


class CommitmentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    recipient: str | None = Field(default=None, max_length=200)
    details: str | None = Field(default=None, max_length=5000)
    status: Status | None = None
    priority: Priority | None = None
    due_at: datetime | None = None
    due_local_date: date | None = None
    due_local_time: time | None = None
    deadline_precision: Precision | None = None
    timezone: str | None = Field(default=None, max_length=64)
    depends_on_ids: list[uuid.UUID] | None = None

    @field_validator("due_at")
    @classmethod
    def _due_at_utc(cls, v: datetime | None) -> datetime | None:
        return as_utc(v)


class CommitmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    recipient: str | None = None
    details: str | None = None
    status: str
    priority: str
    due_at: datetime | None = None
    due_local_date: date | None = None
    due_local_time: time | None = None
    deadline_precision: str
    timezone: str
    source: str
    original_text: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    depends_on_ids: list[uuid.UUID] = Field(default_factory=list)
    blocked_by: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("due_at", "created_at", "updated_at", "completed_at")
    @classmethod
    def _utc(cls, v: datetime | None) -> datetime | None:
        return as_utc(v)


class ActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    commitment_id: uuid.UUID
    action: str
    detail: dict = Field(default_factory=dict)
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _utc(cls, v: datetime | None) -> datetime | None:
        return as_utc(v)


class DependencyCreate(BaseModel):
    depends_on_id: uuid.UUID


class DashboardRead(BaseModel):
    pending: list[CommitmentRead] = Field(default_factory=list)
    overdue: list[CommitmentRead] = Field(default_factory=list)
    completed: list[CommitmentRead] = Field(default_factory=list)
    upcoming: list[CommitmentRead] = Field(default_factory=list)
    blocked: list[CommitmentRead] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    next_actions: list["NextAction"] = Field(default_factory=list)
    server_time: datetime


class NextAction(BaseModel):
    commitment: CommitmentRead
    score: float
    reason: str
    blocked: bool = False


class HealthRead(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    database: str
    llm_provider: str
    mcp_transport: str


class ChatTurnMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class CommitmentDraft(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    recipient: str | None = Field(default=None, max_length=200)
    details: str | None = Field(default=None, max_length=5000)
    due_at: str | None = None
    due_local_date: str | None = None
    due_local_time: str | None = None
    deadline_precision: Precision = "none"
    timezone: str = Field(default="UTC", max_length=64)
    priority: Priority = "normal"
    source: str = Field(default="chat", max_length=40)
    original_text: str | None = None


class ChatRequest(BaseModel):
    messages: list[ChatTurnMessage] = Field(min_length=1)
    timezone: str = Field(default="UTC", max_length=64)


class PendingConfirmation(BaseModel):
    kind: Literal["create_commitment"]
    question: str
    draft: CommitmentDraft


class ChatResponse(BaseModel):
    reply: str
    confirmation: PendingConfirmation | None = None
    tools_used: list[str] = Field(default_factory=list)


class ConfirmRequest(BaseModel):
    draft: CommitmentDraft
