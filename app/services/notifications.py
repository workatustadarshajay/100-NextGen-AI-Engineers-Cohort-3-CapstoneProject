from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentAssignment, DocumentStatus, Notification, utc_now


async def add_notification(
    session: AsyncSession,
    *,
    kind: str,
    title: str,
    message: str,
    document_id: int | None = None,
    user_id: int | None = None,
) -> Notification:
    notification = Notification(
        kind=kind,
        title=title,
        message=message,
        document_id=document_id,
        user_id=user_id,
    )
    session.add(notification)
    return notification


async def ensure_overdue_notifications(session: AsyncSession) -> None:
    """Create one reminder for each review waiting longer than 48 hours."""
    overdue_before = utc_now() - timedelta(hours=48)
    result = await session.execute(
        select(Document).where(
            Document.status == DocumentStatus.WORKFLOW_COMPLETED.value,
            Document.updated_at < overdue_before,
        )
    )
    created = False
    for document in result.scalars().all():
        existing = await session.scalar(
            select(Notification.id)
            .where(
                Notification.kind == "review_overdue",
                Notification.document_id == document.id,
            )
            .limit(1)
        )
        if existing is not None:
            continue

        assignment = await session.scalar(
            select(DocumentAssignment).where(DocumentAssignment.document_id == document.id)
        )
        await add_notification(
            session,
            kind="review_overdue",
            title="Review overdue",
            message=f"{document.file_name} has been waiting for review for more than 48 hours.",
            document_id=document.id,
            user_id=assignment.user_id if assignment else None,
        )
        created = True

    if created:
        await session.commit()
