from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models import DocumentStatus
from app.schemas import DashboardResponse
from app.services.analytics import get_dashboard_metrics


router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def status_label(value: str) -> str:
    labels = {
        DocumentStatus.SUMMARISING.value: "Summarising",
        DocumentStatus.WORKFLOW_COMPLETED.value: "Workflow completed",
        DocumentStatus.HITL_COMPLETED.value: "HITL completed",
        DocumentStatus.FAILED.value: "Needs attention",
    }
    return labels.get(value, value.replace("_", " ").title())


templates.env.filters["status_label"] = status_label


async def _require_user(request: Request, session: AsyncSession):
    user = await get_current_user(request, session)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user


@router.get("/api/dashboard", response_model=DashboardResponse)
async def dashboard_metrics(request: Request, session: SessionDep) -> DashboardResponse:
    await _require_user(request, session)
    return await get_dashboard_metrics(session)


@router.get("/dashboard", response_class=HTMLResponse, response_model=None, include_in_schema=False)
async def dashboard_page(request: Request, session: SessionDep) -> HTMLResponse:
    user = await get_current_user(request, session)
    if user is None:
        from fastapi.responses import RedirectResponse

        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    metrics = await get_dashboard_metrics(session)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "active_page": "dashboard",
            "current_user": user,
            "metrics": metrics,
        },
    )
