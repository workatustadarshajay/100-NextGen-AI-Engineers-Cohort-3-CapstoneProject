import asyncio
from pathlib import Path
from math import ceil
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import UPLOADS_DIR, get_session
from app.models import Document, DocumentStatus, utc_now
from app.schemas import (
    DocumentDetailResponse,
    DocumentListItem,
    DocumentPageResponse,
    DocumentStatus as DocumentStatusSchema,
    DeleteDocumentResponse,
    EditDocumentRequest,
    UploadResponse,
)
from app.services.workflow import run_workflow


router = APIRouter(prefix="/api", tags=["documents"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
MAX_FILE_SIZE = 10 * 1024 * 1024
DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 50
VIEWABLE_STATUSES = {
    DocumentStatus.WORKFLOW_COMPLETED.value,
    DocumentStatus.HITL_COMPLETED.value,
}


def _serialize_list_item(document: Document) -> DocumentListItem:
    return DocumentListItem(
        id=document.id,
        file_name=document.file_name,
        status=DocumentStatusSchema(document.status),
        date_received=document.created_at,
        modified=document.updated_at,
    )


def _serialize_detail(document: Document) -> DocumentDetailResponse:
    return DocumentDetailResponse(
        id=document.id,
        file_name=document.file_name,
        status=DocumentStatusSchema(document.status),
        date_received=document.created_at,
        modified=document.updated_at,
        summary=document.summary,
        can_edit=document.status == DocumentStatus.WORKFLOW_COMPLETED.value,
        can_view=document.status in VIEWABLE_STATUSES,
        error_message=document.error_message,
    )


async def _get_document(session: AsyncSession, document_id: int) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return document


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(description="A PDF document")],
    session: SessionDep,
) -> UploadResponse:
    """Store a PDF and queue the summarisation workflow."""
    if not file.filename or Path(file.filename).suffix.lower() != ".pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are accepted",
        )

    contents = await file.read()
    if not contents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded PDF is empty",
        )
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="PDF files must be 10 MB or smaller",
        )

    original_name = Path(file.filename).name
    stored_path = UPLOADS_DIR / f"{uuid4().hex}_{original_name}"
    await asyncio.to_thread(stored_path.write_bytes, contents)

    document = Document(
        file_name=original_name,
        stored_file_path=str(stored_path),
        file_size=len(contents),
        status=DocumentStatus.SUMMARISING.value,
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)

    background_tasks.add_task(run_workflow, document.id, str(stored_path))
    return UploadResponse(
        document=_serialize_list_item(document),
        message="File accepted. Summarisation is in progress.",
    )


@router.get("/display", response_model=DocumentPageResponse)
async def display_documents(
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> DocumentPageResponse:
    """Return one page of status table data, newest first."""
    total = int(await session.scalar(select(func.count()).select_from(Document)) or 0)
    total_pages = max(1, ceil(total / page_size))
    result = await session.execute(
        select(Document)
        .order_by(Document.created_at.desc(), Document.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    status_result = await session.execute(
        select(Document.status, func.count(Document.id)).group_by(Document.status)
    )
    counts = {document_status: count for document_status, count in status_result.all()}
    return DocumentPageResponse(
        items=[_serialize_list_item(document) for document in result.scalars().all()],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        counts=counts,
    )


@router.delete("/documents/{document_id}", response_model=DeleteDocumentResponse)
async def delete_document(
    document_id: int,
    session: SessionDep,
) -> DeleteDocumentResponse:
    """Remove a document record and its stored PDF."""
    document = await _get_document(session, document_id)
    stored_path = Path(document.stored_file_path)
    try:
        stored_path.resolve().relative_to(UPLOADS_DIR.resolve())
    except ValueError:
        stored_path = Path()

    try:
        if stored_path.is_file():
            await asyncio.to_thread(stored_path.unlink)
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The stored PDF could not be removed",
        ) from error

    await session.delete(document)
    await session.commit()
    return DeleteDocumentResponse(id=document_id, message="Document deleted")


@router.get("/display/{document_id}", response_model=DocumentDetailResponse)
async def display_document(document_id: int, session: SessionDep) -> DocumentDetailResponse:
    """Return detail data only after the workflow has produced a reviewable document."""
    document = await _get_document(session, document_id)
    if document.status not in VIEWABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This document is not ready to view",
        )
    return _serialize_detail(document)


@router.post("/summarise/{document_id}", response_model=DocumentListItem)
async def summarise_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    session: SessionDep,
) -> DocumentListItem:
    """Queue the three-function workflow for an existing upload."""
    document = await _get_document(session, document_id)
    if document.status == DocumentStatus.SUMMARISING.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Summarisation is already in progress",
        )
    if document.status in VIEWABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document has already completed the workflow",
        )

    document.status = DocumentStatus.SUMMARISING.value
    document.error_message = None
    document.updated_at = utc_now()
    await session.commit()
    background_tasks.add_task(run_workflow, document.id, document.stored_file_path)
    return _serialize_list_item(document)


@router.patch("/edit/{document_id}", response_model=DocumentDetailResponse)
async def edit_document(
    document_id: int,
    payload: EditDocumentRequest,
    session: SessionDep,
) -> DocumentDetailResponse:
    """Save a reviewer edit while the document is workflow-complete."""
    document = await _get_document(session, document_id)
    if document.status != DocumentStatus.WORKFLOW_COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only workflow-complete documents can be edited",
        )

    document.summary = payload.summary
    document.updated_at = utc_now()
    await session.commit()
    await session.refresh(document)
    return _serialize_detail(document)


@router.post("/submit/{document_id}", response_model=DocumentDetailResponse)
async def submit_document(
    document_id: int,
    session: SessionDep,
) -> DocumentDetailResponse:
    """Lock the reviewed summary and mark it as human-in-the-loop complete."""
    document = await _get_document(session, document_id)
    if document.status != DocumentStatus.WORKFLOW_COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only workflow-complete documents can be submitted",
        )

    document.status = DocumentStatus.HITL_COMPLETED.value
    document.updated_at = utc_now()
    await session.commit()
    await session.refresh(document)
    return _serialize_detail(document)
