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
6. Submit the review to persist `hitlcompleted`. That state is read-only but remains viewable.

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

The inbox filters are preserved while paging and during live status refresh. Failed documents expose the existing `POST /api/summarise/{document_id}` endpoint as a retry action.

The local database is created at `data/documents.db`; uploaded files are stored under `data/uploads/`.

## Service tests

Each workflow service has an independent test file:

```bash
pytest -q tests/test_extract_from_pdf.py
pytest -q tests/test_retrieve_the_docs.py
pytest -q tests/test_summarise_and_generate_test.py
pytest -q tests/test_document_inbox.py
pytest -q tests/test_document_files.py
```
