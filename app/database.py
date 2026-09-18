from collections.abc import AsyncIterator
from pathlib import Path
import os

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
DATABASE_PATH = DATA_DIR / "documents.db"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DATABASE_PATH}")


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


# create_all never alters an existing table, so agent columns are added separately.
AGENT_DOCUMENT_COLUMNS = ("abnormal_findings", "recommendations")


def _missing_document_columns(sync_connection) -> list[str]:
    inspector = inspect(sync_connection)
    if "documents" not in inspector.get_table_names():
        return []
    existing = {column["name"] for column in inspector.get_columns("documents")}
    return [name for name in AGENT_DOCUMENT_COLUMNS if name not in existing]


engine = create_async_engine(DATABASE_URL, echo=False)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Create the local schema for the first run."""
    from app.models import Document, User  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        for column_name in await connection.run_sync(_missing_document_columns):
            await connection.execute(
                text(f"ALTER TABLE documents ADD COLUMN {column_name} JSON")
            )


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield one async database session per request."""
    async with async_session_factory() as session:
        yield session
