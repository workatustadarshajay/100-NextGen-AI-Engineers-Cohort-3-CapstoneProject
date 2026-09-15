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
3. Open a workflow-complete row to edit the generated summary and save it through the edit API.
4. Submit the review to persist `hitlcompleted`. That state is read-only but remains viewable.

## API surface

- `POST /api/upload` stores a PDF and queues summarisation.
- `POST /api/summarise/{document_id}` requeues a failed document.
- `GET /api/display?page=1&page_size=10` returns one page of four-column inbox data and global status counts.
- `GET /api/display/{document_id}` returns reviewable detail data.
- `DELETE /api/documents/{document_id}` removes the PDF and its document record.
- `PATCH /api/edit/{document_id}` saves a workflow-complete summary.
- `POST /api/submit/{document_id}` locks the summary as HITL complete.

The local database is created at `data/documents.db`; uploaded files are stored under `data/uploads/`.
