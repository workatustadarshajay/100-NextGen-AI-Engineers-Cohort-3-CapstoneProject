from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentStatus(str, Enum):
    SUMMARISING = "summarising"
    WORKFLOW_COMPLETED = "workflowcompleted"
    HITL_COMPLETED = "hitlcompleted"
    FAILED = "failed"


class WorkflowEvent(BaseModel):
    timestamp: datetime
    stage: str
    event: str
    duration_ms: float | None = None
    attempt: int | None = None
    message: str | None = None
    error_type: str | None = None


class DocumentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_name: str
    status: DocumentStatus
    date_received: datetime
    modified: datetime
    workflow_stage: str | None = None
    workflow_attempts: int = 0


class DocumentPageResponse(BaseModel):
    items: list[DocumentListItem]
    page: int
    page_size: int
    total: int
    total_pages: int
    counts: dict[str, int]


class DocumentDetailResponse(DocumentListItem):
    summary: str | None = None
    can_edit: bool
    can_view: bool
    error_message: str | None = None
    patient_details: dict | None = None
    medical_details: dict | None = None
    abnormal_findings: list[dict] = Field(default_factory=list)
    recommendations: list[dict] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)
    workflow_events: list[WorkflowEvent] = Field(default_factory=list)


class WorkflowMonitorItem(BaseModel):
    id: int
    file_name: str
    status: DocumentStatus
    workflow_stage: str | None = None
    workflow_attempts: int = 0
    modified: datetime
    error_message: str | None = None
    last_event: WorkflowEvent | None = None


class WorkflowEventsResponse(BaseModel):
    id: int
    status: DocumentStatus
    workflow_stage: str | None = None
    workflow_attempts: int = 0
    events: list[WorkflowEvent] = Field(default_factory=list)


class UploadResponse(BaseModel):
    document: DocumentListItem
    message: str


class DeleteDocumentResponse(BaseModel):
    id: int
    message: str


class ReviewerResponse(BaseModel):
    id: int
    email: str


class BulkDocumentActionRequest(BaseModel):
    document_ids: list[int] = Field(min_length=1, max_length=100)
    action: Literal["delete", "assign", "mark_reviewed"]
    assignee_id: int | None = None


class BulkActionResponse(BaseModel):
    action: str
    affected_count: int
    skipped_count: int
    message: str


class DocumentExportRequest(BaseModel):
    document_ids: list[int] = Field(min_length=1, max_length=100)


class NotificationResponse(BaseModel):
    id: int
    document_id: int | None = None
    kind: str
    title: str
    message: str
    read_at: datetime | None = None
    created_at: datetime


class NotificationPageResponse(BaseModel):
    notifications: list[NotificationResponse]
    unread_count: int


class ReviewerWorkload(BaseModel):
    reviewer: str
    assigned_count: int
    pending_count: int


class DashboardResponse(BaseModel):
    processed_today: int
    average_processing_minutes: float
    pending_reviews: int
    failed_workflows: int
    total_documents: int
    completed_documents: int
    outstanding_documents: int
    status_counts: dict[str, int]
    reviewer_workloads: list[ReviewerWorkload]
    workflow_monitor: list[WorkflowMonitorItem] = Field(default_factory=list)


class EditDocumentRequest(BaseModel):
    summary: str = Field(min_length=1, max_length=100_000)

    @field_validator("summary")
    @classmethod
    def strip_summary(cls, value: str) -> str:
        cleaned_value = value.strip()
        if not cleaned_value:
            raise ValueError("Summary cannot be empty")
        return cleaned_value
