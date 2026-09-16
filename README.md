# Neuron Clinical Document Workflow

A FastAPI, SQLite, HTML, CSS, and JavaScript application for a human-in-the-loop document workflow. The three service functions define clear integration boundaries for extraction, retrieval, and summarisation.

## Run locally

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`. The API documentation is available at `http://127.0.0.1:8000/docs`.

## Workflow

1. Upload a PDF from `/upload`. The record is stored as `summarising` and the workflow runs in the background.
2. The inbox at `/documents` polls the display API until the record becomes `workflowcompleted`.
3. Search by filename or filter by status to focus the inbox on a working queue.
4. Retry a failed document from the inbox to send it through the workflow again.
5. Open a workflow-complete row to edit the generated summary and save it through the edit API.
6. Review the source PDF beside the summary on desktop, or open it in a modal on smaller screens.
7. Submit the review to persist `hitlcompleted`. That state is read-only but remains viewable.
8. Use the operations dashboard at `/dashboard` to monitor throughput, processing time, review queues, failures, and reviewer workload.
9. Select inbox rows to assign documents, mark ready documents as reviewed, export selected records to CSV, or delete multiple documents together.
10. Use the notification bell for processing completion/failure, assignments, submitted reviews, and overdue review reminders.

## API surface

- `POST /api/upload` stores a PDF and queues summarisation.
- `POST /api/summarise/{document_id}` requeues a failed document.
- `GET /api/display?page=1&page_size=5&search=...&status=...` returns one filtered page of inbox data and status counts.
- `GET /api/display/{document_id}` returns reviewable detail data.
- `GET /api/documents/{document_id}/pdf` streams a reviewable PDF inline.
- `GET /api/documents/{document_id}/download` downloads a reviewable PDF.
- `DELETE /api/documents/{document_id}` removes the PDF and its document record.
- `PATCH /api/edit/{document_id}` saves a workflow-complete summary.
- `POST /api/submit/{document_id}` locks the summary as HITL complete.
- `POST /api/documents/bulk` applies `delete`, `assign`, or `mark_reviewed` to up to 100 document IDs.
- `POST /api/documents/export` downloads selected document records as CSV.
- `GET /api/reviewers` lists users available for assignment.
- `GET /api/dashboard` returns operational metrics and reviewer workloads.
- `GET /api/notifications` lists recent notifications and the unread count.
- `POST /api/notifications/{notification_id}/read` marks one notification read.
- `POST /api/notifications/read-all` marks all visible notifications read.

The inbox filters are preserved while paging and during live status refresh. Failed documents expose the existing `POST /api/summarise/{document_id}` endpoint as a retry action.
Assignments are stored separately from document records, and overdue review reminders are de-duplicated per document.

The local database is created at `data/documents.db`; uploaded files are stored under `data/uploads/`.

## Service tests

Each workflow service has an independent test file:

```bash
pytest -q tests/test_extract_from_pdf.py
pytest -q tests/test_retrieve_the_docs.py
pytest -q tests/test_summarise_and_generate_test.py
pytest -q tests/test_document_inbox.py
pytest -q tests/test_document_files.py
pytest -q tests/test_operations.py
```
