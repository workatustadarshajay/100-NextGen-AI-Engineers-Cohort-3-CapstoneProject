from collections import Counter
from math import ceil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models import Document, DocumentStatus, User
from app.routers.documents import DEFAULT_PAGE_SIZE, build_document_filters


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


def username_initials(user) -> str:
    username = (getattr(user, "email", "") or "").split("@", 1)[0].strip()
    return (username[:2] or "NR").upper()


templates.env.filters["status_label"] = status_label
templates.env.filters["format_datetime"] = format_datetime
templates.env.filters["username_initials"] = username_initials


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
    page: int = Query(default=1, ge=1),
    search: str | None = Query(default=None, max_length=255),
    status_filter: DocumentStatus | None = Query(default=None, alias="status"),
) -> HTMLResponse | RedirectResponse:
    user = await get_current_user(request, session)
    if user is None:
        return _login_redirect()

    filters = build_document_filters(search, status_filter)
    count_query = select(func.count()).select_from(Document)
    document_query = select(Document).order_by(
        Document.created_at.desc(), Document.id.desc()
    )
    status_query = select(Document.status, func.count(Document.id)).group_by(Document.status)
    if filters:
        count_query = count_query.where(*filters)
        document_query = document_query.where(*filters)
        status_query = status_query.where(*filters)

    total_documents = int(await session.scalar(count_query) or 0)
    total_pages = max(1, ceil(total_documents / DEFAULT_PAGE_SIZE))
    page = min(page, total_pages)
    result = await session.execute(
        document_query
        .offset((page - 1) * DEFAULT_PAGE_SIZE)
        .limit(DEFAULT_PAGE_SIZE)
    )
    documents = result.scalars().all()
    status_result = await session.execute(status_query)
    counts = Counter(dict(status_result.all()))
    reviewer_result = await session.execute(select(User).order_by(User.email))
    reviewers = reviewer_result.scalars().all()
    return templates.TemplateResponse(
        request=request,
        name="documents.html",
        context={
            "active_page": "documents",
            "documents": documents,
            "counts": counts,
            "page": page,
            "page_size": DEFAULT_PAGE_SIZE,
            "total_documents": total_documents,
            "total_pages": total_pages,
            "search": (search or "").strip(),
            "status_filter": status_filter.value if status_filter else "",
            "reviewers": reviewers,
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
