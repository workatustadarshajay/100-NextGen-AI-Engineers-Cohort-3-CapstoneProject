from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models import Document, DocumentStatus


router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")
VIEWABLE_STATUSES = {
    DocumentStatus.WORKFLOW_COMPLETED.value,
    DocumentStatus.HITL_COMPLETED.value,
}
STATUS_LABELS = {
    DocumentStatus.SUMMARISING.value: "Summarising",
    DocumentStatus.WORKFLOW_COMPLETED.value: "Workflow completed",
    DocumentStatus.HITL_COMPLETED.value: "HITL completed",
    DocumentStatus.FAILED.value: "Needs attention",
}


def status_label(value: str) -> str:
    return STATUS_LABELS.get(value, value.replace("_", " ").title())


def format_datetime(value) -> str:
    return value.strftime("%d %b %Y, %H:%M") if value else "-"


templates.env.filters["status_label"] = status_label
templates.env.filters["format_datetime"] = format_datetime


def _login_redirect() -> RedirectResponse:
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/", include_in_schema=False)
async def home() -> RedirectResponse:
    return RedirectResponse(url="/documents", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/upload", response_class=HTMLResponse, response_model=None, include_in_schema=False)
async def upload_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse | RedirectResponse:
    user = await get_current_user(request, session)
    if user is None:
        return _login_redirect()
    return templates.TemplateResponse(
        request=request,
        name="upload.html",
        context={"active_page": "upload", "current_user": user},
    )


@router.get("/documents", response_class=HTMLResponse, response_model=None, include_in_schema=False)
async def documents_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse | RedirectResponse:
    user = await get_current_user(request, session)
    if user is None:
        return _login_redirect()
    result = await session.execute(select(Document).order_by(Document.created_at.desc()))
    documents = result.scalars().all()
    counts = Counter(document.status for document in documents)
    return templates.TemplateResponse(
        request=request,
        name="documents.html",
        context={
            "active_page": "documents",
            "documents": documents,
            "counts": counts,
            "notice": request.query_params.get("notice"),
            "current_user": user,
        },
    )


@router.get(
    "/documents/{document_id}",
    response_class=HTMLResponse,
    response_model=None,
    include_in_schema=False,
)
async def document_detail_page(
    document_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse | RedirectResponse:
    user = await get_current_user(request, session)
    if user is None:
        return _login_redirect()
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if document.status not in VIEWABLE_STATUSES:
        return RedirectResponse(url="/documents?notice=locked", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="document_detail.html",
        context={
            "active_page": "documents",
            "document": document,
            "is_editable": document.status == DocumentStatus.WORKFLOW_COMPLETED.value,
            "current_user": user,
        },
    )
