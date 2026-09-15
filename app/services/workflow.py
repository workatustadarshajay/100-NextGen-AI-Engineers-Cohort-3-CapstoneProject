import asyncio
from datetime import datetime, timezone

from app.database import async_session_factory
from app.models import Document, DocumentStatus
from app.services.extract_from_pdf import extract_from_pdf
from app.services.retrieve_the_docs import retrieve_the_docs
from app.services.summarise_and_generate_test import summarise_and_generate_test


async def run_workflow(document_id: int, file_path: str) -> None:
    """Run the three workflow stages and persist the generated summary."""
    async with async_session_factory() as session:
        document = await session.get(Document, document_id)
        if document is None or document.status == DocumentStatus.HITL_COMPLETED.value:
            return

        try:
            patient_details, medical_details = await asyncio.to_thread(
                extract_from_pdf, file_path
            )
            reference_docs = await asyncio.to_thread(
                retrieve_the_docs, medical_details
            )
            summary = await asyncio.to_thread(
                summarise_and_generate_test,
                patient_details,
                medical_details,
                reference_docs,
            )
            document.summary = summary
            document.status = DocumentStatus.WORKFLOW_COMPLETED.value
            document.error_message = None
        except Exception as error:
            document.status = DocumentStatus.FAILED.value
            document.error_message = str(error)
        document.updated_at = datetime.now(timezone.utc)
        await session.commit()
