from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DocumentStatus(str, Enum):
    SUMMARISING = "summarising"
    WORKFLOW_COMPLETED = "workflowcompleted"
    HITL_COMPLETED = "hitlcompleted"
    FAILED = "failed"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
        default=DocumentStatus.SUMMARISING.value,
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient_details: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    medical_details: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    reference_docs: Mapped[list[dict[str, str]] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
