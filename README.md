# Neuron Clinical Document Workflow

An AI clinical report summarization assistant. FastAPI, SQLite, and vanilla JavaScript drive a
human-in-the-loop review workflow, powered by a sequential LangGraph agent pipeline that runs on
Gemini and is grounded by retrieval over a medical guideline corpus.

> AI-generated clinical decision support. Not a diagnosis. A qualified clinician reviews and signs
> off every document.

## Agent architecture

```
upload PDF -> [Report Analysis Agent] -> [Guideline RAG] -> [Summary Agent] -> [Recommendation Agent] -> human review
```

| Stage | Module | Output |
| --- | --- | --- |
| Report Analysis Agent | `app/services/extract_from_pdf.py` | `ReportAnalysis` with patient profile and flagged lab findings |
| Guideline RAG | `app/services/retrieve_the_docs.py` | `GuidelineCitation` list from ChromaDB |
| Summary Agent | `app/services/summarise_and_generate_test.py` | `ClinicalSummary` |
| Recommendation Agent | `app/services/recommend_follow_ups.py` | Prioritised `Recommendation` list |
| Orchestration | `app/services/agents/graph.py` | Sequential `StateGraph` with retries and an error handler |

Each node carries a `RetryPolicy`; permanent faults (missing API key, unreadable PDF) are not
retried. When a node exhausts its retries the graph's `error_handler` records the failure and the
document is marked `failed` rather than crashing the request.

## Run locally

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then set GEMINI_API_KEY
python scripts/generate_synthetic_data.py
python scripts/ingest_guidelines.py

uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`. The API documentation is available at `http://127.0.0.1:8000/docs`.

`GEMINI_API_KEY` is required. Without it an upload is marked `failed` with an explanatory message.
Keys are read from the environment or `.env` only, and `.env` is gitignored.

## Synthetic data and the guideline index

- `scripts/generate_synthetic_data.py` writes 10 guideline PDFs to `data/guidelines/` and 25
  seeded synthetic patient and lab reports to `data/synthetic/reports/`. No real patient data is used.
- `scripts/ingest_guidelines.py` chunks those guidelines by section, embeds them with
  `gemini-embedding-001`, and indexes them in ChromaDB at `data/chroma/`. Re-running rebuilds the index.

## Workflow

1. Upload a PDF from `/upload`. The record is stored as `summarising` and the agent graph runs in the background.
2. The inbox at `/documents` polls the display API until the record becomes `workflowcompleted`.
3. Search by filename or filter by status to focus the inbox on a working queue.
4. Retry a failed document from the inbox to send it through the workflow again.
5. Open a workflow-complete row to review the generated summary, abnormal findings, follow-up
   recommendations, and guideline citations, and to edit the summary.
6. Review the source PDF beside the summary on desktop, or open it in a modal on smaller screens.
7. Submit the review to persist `hitlcompleted`. That state is read-only but remains viewable.
8. Use the operations dashboard at `/dashboard` to monitor throughput, processing time, review queues, failures, and reviewer workload.
9. Select inbox rows to assign documents, mark ready documents as reviewed, export selected records to CSV, or delete multiple documents together.
10. Use the notification bell for processing completion/failure, critical findings, assignments, submitted reviews, and overdue review reminders.

## API surface

- `POST /api/upload` stores a PDF and queues the agent workflow.
- `POST /api/summarise/{document_id}` requeues a failed document.
- `GET /api/display?page=1&page_size=5&search=...&status=...` returns one filtered page of inbox data and status counts.
- `GET /api/display/{document_id}` returns reviewable detail data, including findings, recommendations, and citations.
- `GET /api/documents/{document_id}/pdf` streams a reviewable PDF inline.
- `GET /api/documents/{document_id}/download` downloads a reviewable PDF.
- `DELETE /api/documents/{document_id}` removes the PDF and its document record.
- `PATCH /api/edit/{document_id}` saves a workflow-complete summary.
- `POST /api/submit/{document_id}` locks the summary as HITL complete.
- `POST /api/documents/bulk` applies `delete`, `assign`, or `mark_reviewed` to up to 100 document IDs.
- `POST /api/documents/export` downloads selected document records as CSV, including abnormal counts and top priority.
- `GET /api/reviewers` lists users available for assignment.
- `GET /api/dashboard` returns operational metrics and reviewer workloads.
- `GET /api/notifications` lists recent notifications and the unread count.
- `POST /api/notifications/{notification_id}/read` marks one notification read.
- `POST /api/notifications/read-all` marks all visible notifications read.

The inbox filters are preserved while paging and during live status refresh. Failed documents expose the existing `POST /api/summarise/{document_id}` endpoint as a retry action.
Assignments are stored separately from document records, and overdue review reminders are de-duplicated per document.

The local database is created at `data/documents.db`; uploaded files are stored under `data/uploads/`.

## Tests

The suite runs fully offline. The Gemini client is injected, so no test reaches the network.

```bash
pytest -q tests
```
