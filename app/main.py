import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.database import engine, init_db
from app.routers.auth import router as auth_router
from app.routers.documents import router as documents_router
from app.routers.pages import router as pages_router


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
    secret_key=os.getenv("SESSION_SECRET", "dev-only-insecure-secret"),
)

static_directory = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_directory), name="static")
app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(pages_router)
