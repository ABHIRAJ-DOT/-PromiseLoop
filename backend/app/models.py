"""SQLAlchemy models. Single source of truth for the schema.

The same metadata is rendered to Postgres DDL in ``app/schema_sql.py`` so the
Supabase SQL editor and the app can never drift apart.
"""

import uuid
from datetime import date, datetime, time, timezone

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    commitments: Mapped[list["Commitment"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Commitment(Base):
    __tablename__ = "commitments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    recipient: Mapped[str | None] = mapped_column(String(200), default=None)
    details: Mapped[str | None] = mapped_column(Text, default=None)

    status: Mapped[str] = mapped_column(String(20), default="pending", index=True, nullable=False)
    priority: Mapped[str] = mapped_column(String(10), default="normal", nullable=False)

    # Absolute instant (UTC) plus the local calendar date the user actually
    # said, so "tomorrow evening" survives timezone maths and display.
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None, index=True)
    due_local_date: Mapped[date | None] = mapped_column(Date, default=None)
    due_local_time: Mapped[time | None] = mapped_column(Time, default=None)
    deadline_precision: Mapped[str] = mapped_column(String(10), default="none", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)

    source: Mapped[str] = mapped_column(String(20), default="chat", nullable=False)
    original_text: Mapped[str | None] = mapped_column(Text, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    user: Mapped[User] = relationship(back_populates="commitments")

    __table_args__ = (
        Index("ix_commitments_user_status_due", "user_id", "status", "due_at"),
    )


class CommitmentDependency(Base):
    """``commitment_id`` cannot start until ``depends_on_id`` is done."""

    __tablename__ = "commitment_dependencies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    commitment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("commitments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    depends_on_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("commitments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("commitment_id", "depends_on_id", name="uq_dependency"),)


class Activity(Base):
    """Append-only history of everything that happened to a commitment."""

    __tablename__ = "activity"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    commitment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("commitments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (Index("ix_activity_commitment_created", "commitment_id", "created_at"),)
