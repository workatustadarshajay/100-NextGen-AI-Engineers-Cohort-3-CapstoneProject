from datetime import datetime, timezone

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentAssignment, DocumentStatus, User
from app.schemas import DashboardResponse, ReviewerWorkload, WorkflowEvent, WorkflowMonitorItem


async def get_dashboard_metrics(session: AsyncSession) -> DashboardResponse:
    now = datetime.now(timezone.utc)
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    completed_statuses = (
        DocumentStatus.WORKFLOW_COMPLETED.value,
        DocumentStatus.HITL_COMPLETED.value,
    )

    total_documents = int(await session.scalar(select(func.count()).select_from(Document)) or 0)
    completed_documents = int(
        await session.scalar(
            select(func.count()).select_from(Document).where(
                Document.status == DocumentStatus.HITL_COMPLETED.value
            )
        )
        or 0
    )
    processed_today = int(
        await session.scalar(
            select(func.count()).select_from(Document).where(
                Document.status.in_(completed_statuses),
                Document.workflow_completed_at >= start_of_today,
            )
        )
        or 0
    )
    pending_reviews = int(
        await session.scalar(
            select(func.count()).select_from(Document).where(
                Document.status == DocumentStatus.WORKFLOW_COMPLETED.value
            )
        )
        or 0
    )
    failed_workflows = int(
        await session.scalar(
            select(func.count()).select_from(Document).where(
                Document.status == DocumentStatus.FAILED.value
            )
        )
        or 0
    )

    duration_minutes = (
        func.julianday(Document.workflow_completed_at)
        - func.julianday(Document.workflow_started_at)
    ) * 24 * 60
    average_processing_minutes = float(
        await session.scalar(
            select(func.avg(duration_minutes)).where(
                Document.status.in_(completed_statuses),
                Document.workflow_started_at.is_not(None),
                Document.workflow_completed_at.is_not(None),
            )
        )
        or 0
    )

    status_result = await session.execute(
        select(Document.status, func.count(Document.id)).group_by(Document.status)
    )
    status_counts = {document_status: count for document_status, count in status_result.all()}

    pending_case = case(
        (Document.status == DocumentStatus.WORKFLOW_COMPLETED.value, 1),
        else_=0,
    )
    reviewer_result = await session.execute(
        select(
            User.email,
            func.count(DocumentAssignment.id),
            func.coalesce(func.sum(pending_case), 0),
        )
        .join(DocumentAssignment, DocumentAssignment.user_id == User.id)
        .join(Document, Document.id == DocumentAssignment.document_id)
        .group_by(User.id, User.email)
        .order_by(func.count(DocumentAssignment.id).desc(), User.email)
    )
    reviewer_workloads = [
        ReviewerWorkload(
            reviewer=email,
            assigned_count=int(assigned_count),
            pending_count=int(pending_count),
        )
        for email, assigned_count, pending_count in reviewer_result.all()
    ]

    monitor_result = await session.execute(
        select(Document)
        .order_by(Document.updated_at.desc(), Document.id.desc())
        .limit(8)
    )
    workflow_monitor = []
    for document in monitor_result.scalars().all():
        last_event = None
        if document.workflow_events:
            try:
                last_event = WorkflowEvent.model_validate(document.workflow_events[-1])
            except (TypeError, ValueError):
                last_event = None
        workflow_monitor.append(
            WorkflowMonitorItem(
                id=document.id,
                file_name=document.file_name,
                status=document.status,
                workflow_stage=document.workflow_stage,
                workflow_attempts=document.workflow_attempts or 0,
                modified=document.updated_at,
                error_message=document.error_message,
                last_event=last_event,
            )
        )

    return DashboardResponse(
        processed_today=processed_today,
        average_processing_minutes=round(average_processing_minutes, 1),
        pending_reviews=pending_reviews,
        failed_workflows=failed_workflows,
        total_documents=total_documents,
        completed_documents=completed_documents,
        outstanding_documents=max(total_documents - completed_documents, 0),
        status_counts=status_counts,
        reviewer_workloads=reviewer_workloads,
        workflow_monitor=workflow_monitor,
    )
