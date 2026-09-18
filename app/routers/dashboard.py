from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.schemas import DashboardResponse
from app.services.analytics import get_dashboard_metrics
from app.templating import create_templates


router = APIRouter(tags=["dashboard"])
templates = create_templates()
SessionDep = Annotated[AsyncSession, Depends(get_session)]


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
