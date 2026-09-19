# Neuron Clinical Document Workflow

An AI clinical report summarization assistant. FastAPI, SQLite, and vanilla JavaScript drive a
human-in-the-loop review workflow, powered by a LangGraph agent pipeline with sequential stages,
parallel routing, and retrieval over a medical guideline corpus.

> AI-generated clinical decision support. Not a diagnosis. A qualified clinician reviews and signs
> off every document.

## Agent architecture

```
upload PDF -> [Report Analysis Agent]
                    |\
                    | +--> [Risk Router] -> [Urgent Review Lane]
                    |                    \-> [Standard Review Lane]
                    +----> [Guideline RAG]
                              \            /
                               +-- [Summary Agent] -> [Recommendation Agent] -> human review
```

| Stage | Module | Output |
| --- | --- | --- |
| Report Analysis Agent | `app/services/extract_from_pdf.py` | `ReportAnalysis` with patient profile and flagged lab findings |
| Guideline RAG | `app/services/retrieve_the_docs.py` | `GuidelineCitation` list from ChromaDB |
| Summary Agent | `app/services/summarise_and_generate_test.py` | `ClinicalSummary` |
| Recommendation Agent | `app/services/recommend_follow_ups.py` | Prioritised `Recommendation` list |
| Orchestration | `app/services/agents/graph.py` | Sequential `StateGraph` with parallel fan-out, risk routing, bounded retries, and an error handler |

The analysis stage fans out to guideline retrieval and a risk router. The router selects an urgent
or standard review lane, and an explicit fan-in barrier prevents summary generation until both the
retrieval and selected lane complete. Each node carries a bounded `RetryPolicy`; permanent faults
(missing API key, unreadable PDF, invalid model output, and quota exhaustion) are not retried. When
a node exhausts its retries the graph's `error_handler` records the failure and the document is
marked `failed` rather than crashing the request.

Every workflow writes structured JSON logs to the console and rotating `data/logs/neuron.log`.
Document records also retain stage, attempt count, timestamps, safe error text, and event timings.
The live dashboard polls `/api/dashboard` and displays the current agent stage while processing.
All document and operations APIs require an authenticated session. Production startup also
requires `APP_ENV=production` to be paired with a configured `SESSION_SECRET`.

LangGraph execution is traced to the LangSmith project `my-first-agent` when
`LANGSMITH_API_KEY` is configured. The local environment enables both current and legacy
tracing flags for SDK compatibility, names workflow roots `clinical_document_workflow`, and
records document IDs as metadata. Trace inputs and outputs are hidden by default because the
workflow handles clinical documents. The LangSmith skills are installed under `.agents/skills/`.
If a corporate HTTPS proxy replaces certificates, set `REQUESTS_CA_BUNDLE` to the trusted PEM
bundle path; do not disable TLS verification.

## Run locally

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then set the API keys and a long random SESSION_SECRET
# Set LANGSMITH_API_KEY in the environment or local .env to enable LangSmith uploads.
python scripts/generate_synthetic_data.py
python scripts/ingest_guidelines.py

uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`. The API documentation is available at `http://127.0.0.1:8000/docs`.

### Run with Docker

```bash
cp .env.example .env          # then set GEMINI_API_KEY and a long random SESSION_SECRET
SEED_SYNTHETIC_DATA=1 INGEST_GUIDELINES=1 docker compose up --build -d
```

The compose file builds the image, mounts a named volume at `/app/data` (SQLite database, uploads,
ChromaDB index, and logs), and exposes port `8000`. On the first run set `SEED_SYNTHETIC_DATA=1` to
generate the synthetic PDF corpus and `INGEST_GUIDELINES=1` to build the guideline index; both flags
are safe to remove afterwards. A liveness probe is exposed at `GET /health`.

`GEMINI_API_KEY` is required. Without it an upload is marked `failed` with an explanatory message.
Keys are read from the environment or `.env` only, and `.env` is gitignored.
Set `TRUSTED_SEARCH_ENABLED=1` to enable the opt-in fallback search over guideline-like records in
Europe PMC/PubMed when the local Chroma corpus has no sufficiently relevant match. The search is
restricted to the allowlisted Europe PMC endpoint, sends only the clinical concern and finding
names, and stores the source URL, publication date, and age label for reviewer inspection. A source
age label is review metadata, not a claim that older guidance is invalid.
The default model is `gemini-3.8-flash`. A Gemini `429` quota error means the configured project
has exhausted its available request quota; the workflow does not retry that exhausted quota. Wait
for the quota window to reset, or enable billing/use a project with available quota. Changing the
model only helps when the selected model has separate available quota.
Set `GROQ_API_KEY` to enable the automatic text-generation fallback when Gemini returns HTTP 429.
The fallback uses `llama-3.3-70b-versatile` by default and validates its JSON against the same
Pydantic schemas. Groq replaces Gemini generation only; guideline embeddings still use the
configured Gemini embedding model. `RAG_MIN_RELEVANCE_SCORE` filters weak Chroma matches before
they reach the summary and recommendation agents; the default is `0.2`.

## Synthetic data and the guideline index

- `scripts/generate_synthetic_data.py` writes 10 guideline PDFs to `data/guidelines/` and 25
  seeded synthetic patient and lab reports to `data/synthetic/reports/`. No real patient data is used.
- `scripts/ingest_guidelines.py` chunks those guidelines by section, embeds them with
  `gemini-embedding-001`, and indexes them in ChromaDB at `data/chroma/`. Re-running rebuilds the index.

## Workflow

1. Upload a PDF from `/upload`. The record is stored as `summarising`, the user returns to `/dashboard`, and the agent graph runs in the background.
2. The dashboard monitor polls `/api/dashboard` until the record becomes `workflowcompleted` or `failed`.
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
- `PATCH /api/edit/{document_id}` reconciles and atomically saves a workflow-complete summary with its dependent structured findings.
- `POST /api/submit/{document_id}` locks the summary as HITL complete.
- `POST /api/documents/bulk` applies `delete`, `assign`, or `mark_reviewed` to up to 100 document IDs.
- `POST /api/documents/export` downloads selected document records as CSV, including abnormal counts and top priority.
- `GET /api/reviewers` lists users available for assignment.
- `GET /api/dashboard` returns operational metrics and reviewer workloads.
- `GET /api/documents/{document_id}/workflow-events` returns authenticated stage timings and failure events.
- `GET /api/notifications` lists recent notifications and the unread count.
- `POST /api/notifications/{notification_id}/read` marks one notification read.
- `POST /api/notifications/read-all` marks all visible notifications read.

The inbox filters are preserved while paging and during live status refresh. Failed documents expose the existing `POST /api/summarise/{document_id}` endpoint as a retry action.
Assignments are stored separately from document records, and overdue review reminders are de-duplicated per document.

The local database is created at `data/documents.db`; uploaded files are stored under `data/uploads/`.

## Tests

The suite runs fully offline. Gemini and Groq clients are injected, so no test reaches either provider.

```bash
pytest -q tests
```
