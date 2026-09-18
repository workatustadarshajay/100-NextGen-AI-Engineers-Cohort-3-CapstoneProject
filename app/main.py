import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.database import engine, init_db
from app.observability import configure_logging
from app.routers.auth import router as auth_router
from app.routers.dashboard import router as dashboard_router
from app.routers.documents import router as documents_router
from app.routers.notifications import router as notifications_router
from app.routers.pages import router as pages_router


configure_logging()

APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
SESSION_SECRET = (os.getenv("SESSION_SECRET") or "").strip()
if APP_ENV in {"production", "prod"} and not SESSION_SECRET:
    raise RuntimeError("SESSION_SECRET must be configured when APP_ENV is production")
SESSION_SECRET = SESSION_SECRET or "dev-only-insecure-secret"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await init_db()
    yield
    await engine.dispose()


app = FastAPI(
    title="Neuron Clinical Document Workflow",
    description="A human-in-the-loop document summarisation workflow.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
)

static_directory = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_directory), name="static")
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(documents_router)
app.include_router(notifications_router)
app.include_router(pages_router)
