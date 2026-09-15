from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password, verify_password
from app.database import get_session
from app.models import User


router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/login", response_class=HTMLResponse, response_model=None, include_in_schema=False)
async def login_page(request: Request) -> HTMLResponse | RedirectResponse:
    if request.session.get("user_id"):
        return RedirectResponse(url="/documents", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="login.html", context={})


@router.post("/login", response_model=None, include_in_schema=False)
async def login(
    request: Request,
    session: SessionDep,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> HTMLResponse | RedirectResponse:
    result = await session.execute(select(User).where(User.email == email.strip().lower()))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"login_error": "Invalid email or password", "login_email": email},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    request.session["user_id"] = user.id
    return RedirectResponse(url="/documents", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/register", response_model=None, include_in_schema=False)
async def register(
    request: Request,
    session: SessionDep,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> HTMLResponse | RedirectResponse:
    email = email.strip().lower()
    if "@" not in email:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"register_error": "Enter a valid email address", "register_email": email, "active_tab": "register"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if len(password) < 8:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "register_error": "Password must be at least 8 characters",
                "register_email": email,
                "active_tab": "register",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    existing = await session.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "register_error": "An account with that email already exists",
                "register_email": email,
                "active_tab": "register",
            },
            status_code=status.HTTP_409_CONFLICT,
        )

    user = User(email=email, password_hash=hash_password(password))
    session.add(user)
    await session.commit()
    await session.refresh(user)

    request.session["user_id"] = user.id
    return RedirectResponse(url="/documents", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout", include_in_schema=False)
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
