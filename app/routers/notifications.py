from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models import Notification, utc_now
from app.schemas import NotificationPageResponse, NotificationResponse
from app.services.notifications import ensure_overdue_notifications


router = APIRouter(prefix="/api/notifications", tags=["notifications"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _require_user(request: Request, session: AsyncSession):
    user = await get_current_user(request, session)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user


def _serialize(notification: Notification) -> NotificationResponse:
    return NotificationResponse(
        id=notification.id,
        document_id=notification.document_id,
        kind=notification.kind,
        title=notification.title,
        message=notification.message,
        read_at=notification.read_at,
        created_at=notification.created_at,
    )


@router.get("", response_model=NotificationPageResponse)
async def list_notifications(
    request: Request,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 8,
) -> NotificationPageResponse:
    user = await _require_user(request, session)
    await ensure_overdue_notifications(session)
    visible = or_(Notification.user_id.is_(None), Notification.user_id == user.id)
    result = await session.execute(
        select(Notification)
        .where(visible)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
    )
    unread_count = int(
        await session.scalar(
            select(func.count(Notification.id)).where(visible, Notification.read_at.is_(None))
        )
        or 0
    )
    return NotificationPageResponse(
        notifications=[_serialize(notification) for notification in result.scalars().all()],
        unread_count=unread_count,
    )


@router.post("/read-all")
async def mark_all_notifications_read(request: Request, session: SessionDep) -> dict[str, int]:
    user = await _require_user(request, session)
    visible = or_(Notification.user_id.is_(None), Notification.user_id == user.id)
    result = await session.execute(
        update(Notification)
        .where(visible, Notification.read_at.is_(None))
        .values(read_at=utc_now())
    )
    await session.commit()
    return {"updated": result.rowcount or 0}


@router.post("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: int,
    request: Request,
    session: SessionDep,
) -> NotificationResponse:
    user = await _require_user(request, session)
    notification = await session.get(Notification, notification_id)
    if notification is None or notification.user_id not in (None, user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    if notification.read_at is None:
        notification.read_at = utc_now()
        await session.commit()
        await session.refresh(notification)
    return _serialize(notification)
