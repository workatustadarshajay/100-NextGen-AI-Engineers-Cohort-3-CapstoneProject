from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentStatus(str, Enum):
    SUMMARISING = "summarising"
    WORKFLOW_COMPLETED = "workflowcompleted"
    HITL_COMPLETED = "hitlcompleted"
    FAILED = "failed"


class DocumentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_name: str
    status: DocumentStatus
    date_received: datetime
    modified: datetime


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


class UploadResponse(BaseModel):
    document: DocumentListItem
    message: str


class DeleteDocumentResponse(BaseModel):
    id: int
    message: str


class EditDocumentRequest(BaseModel):
    summary: str = Field(min_length=1, max_length=100_000)

    @field_validator("summary")
    @classmethod
    def strip_summary(cls, value: str) -> str:
        cleaned_value = value.strip()
        if not cleaned_value:
            raise ValueError("Summary cannot be empty")
        return cleaned_value
