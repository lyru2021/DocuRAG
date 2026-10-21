# DocuRAG

**A source-aware document retrieval and research-agent backend built with FastAPI, PostgreSQL, Celery, and LangGraph.**

DocuRAG ingests academic PDFs, extracts page-linked text, splits it into searchable chunks, and exposes evidence retrieval through HTTP APIs and bounded research-agent tools. The project prioritizes traceable evidence, controlled tool execution, reproducible tests, and local-first deployment.

> **Project status:** Working Docker Compose backend with asynchronous PDF processing, PostgreSQL text search, API-key authentication, request tracing, automated CI, and a separately validated scripted-Mock Agent → real-database tool chain. Semantic answer accuracy and vector search are **not** claimed.

## Features

- **Document ingestion:** Upload PDF documents; extract text with page mapping, character offsets, and chunk overlap. Synchronous document upload also supports TXT files.
- **Asynchronous processing:** FastAPI accepts PDF uploads, Redis brokers jobs, Celery workers parse and persist results, and Celery Beat helps recover pending work.
- **Evidence-aware storage:** PostgreSQL stores documents, paper metadata, page text, chunks, and processing-job records. Original PDF files are retained in a shared Docker volume.
- **Text retrieval:** PostgreSQL-backed literal and full-text search (FTS), plus paper metadata queries and exact chunk-evidence lookup.
- **Bounded research agent:** Whitelisted `search_papers`, `search_chunks`, and `get_evidence` tools; validated arguments, call budgets, read-only database transactions, and per-query SQL statement timeouts.
- **Multi-step research workflow:** A LangGraph-based pipeline for cross-paper retrieval, structured fact extraction, exact-quote checks, evidence coverage assessment, and a bounded supplementary retrieval round.
- **Operational safeguards:** API-key authentication on business endpoints, `X-Request-ID` tracing, structured HTTP logs, migration-controlled schemas, and isolated automated tests.
- **CI:** GitHub Actions provisions a fresh PostgreSQL/Redis test environment, applies Alembic migrations, and runs the test suite without a paid LLM provider.

### Not implemented or not yet established

Vector embeddings / pgvector similarity retrieval, OCR for image-only or scanned PDFs, production-grade multi-user authorization and document ownership, and independently validated semantic correctness of research answers are **not** currently established features. The PostgreSQL Docker image includes pgvector, but image support alone does not imply vector retrieval is implemented.

## Architecture

```mermaid
flowchart TD
    Client[Client / Swagger UI] --> API[FastAPI + API Key + Request ID]
    API --> DB[(PostgreSQL: metadata, pages, chunks, jobs)]
    API --> Redis[(Redis broker)]
    Redis --> Worker[Celery Worker: PDF processing]
    Beat[Celery Beat: scheduled recovery] --> Redis
    Worker --> DB
    API --> Agent[Research Agent / LangGraph workflows]
    Agent --> Executor[ToolRegistry + ToolExecutor]
    Executor --> DB
    Agent --> LLM[Mock / configured model adapter]
    API --> Volume[(Shared PDF volume)]
    Worker --> Volume
```

Docker Compose runs six services: `postgres`, `redis`, `migrate` (one-shot Alembic upgrade), `api`, `worker`, and `beat`. PostgreSQL and Redis are internal-only in the supplied Compose configuration; the API is published to `127.0.0.1:8000`.

## Technology stack

| Layer | Technology |
|---|---|
| API and validation | Python 3.11, FastAPI, Pydantic |
| Database | PostgreSQL 16, SQLAlchemy, Alembic |
| Search | PostgreSQL literal matching and full-text search (`pg_trgm` indexes) |
| Asynchronous jobs | Redis 7, Celery worker, Celery Beat |
| PDF processing | PyMuPDF |
| Research workflow | LangGraph, bounded tool executor, Mock / optional model adapters |
| Testing / CI | pytest, GitHub Actions |
| Deployment | Docker, Docker Compose, named volumes |

## Quick start: Docker Compose

**Prerequisites:** Docker with Compose support, Git, and a checked-out copy of this repository. Under Windows, WSL Ubuntu with Docker Desktop WSL integration is supported.

1. **Prepare local Docker configuration.** Create `.env.docker` in the repository root. It is intentionally local and **must not be committed**. For a new local installation, the following snippet generates a random hex-only password and API key and writes a suitable configuration:

   ```bash
   python3 - <<'PY'
   from pathlib import Path
   import secrets

   path = Path('.env.docker')
   if path.exists():
       raise SystemExit('.env.docker already exists; leave its current credentials unchanged')

   password = secrets.token_hex(16)
   key = secrets.token_hex(32)
   db_url = f'postgresql+psycopg://docurag:{password}@postgres:5432/docurag'
   path.write_text(
       '\n'.join([
           'POSTGRES_DB=docurag',
           'POSTGRES_USER=docurag',
           f'POSTGRES_PASSWORD={password}',
           f'DATABASE_URL={db_url}',
           f'MIGRATION_DATABASE_URL={db_url}',
           'REDIS_URL=redis://redis:6379/0',
           'APP_ENV=development',
           'DEBUG=false',
           'LLM_PROVIDER=mock',
           'AUTH_ENABLED=true',
           f'DOCURAG_API_KEY={key}',
           '',
       ]), encoding='utf-8',
   )
   path.chmod(0o600)
   print('Created .env.docker with random local credentials; values not printed')
   PY
   ```

   Keep `DATABASE_URL` and `MIGRATION_DATABASE_URL` pointed at the same intended database. If reusing a persistent PostgreSQL volume, **do not change its password in `.env.docker` without also updating the actual database credentials**.

2. **Build the application image** (the current Compose file uses an image tag; it does not contain a `build:` directive):

   ```bash
   docker build -t docurag:day13 .
   ```

3. **Start the stack:**

   ```bash
   docker compose --env-file .env.docker up -d
   docker compose --env-file .env.docker ps
   curl -i http://127.0.0.1:8000/health
   ```

   The `migrate` service is expected to exit successfully after `alembic upgrade head`; the long-running services should remain healthy/running. API documentation is available at <http://127.0.0.1:8000/docs>.

4. **Inspect logs and stop without deleting data:**

   ```bash
   docker compose --env-file .env.docker logs --tail=100 api worker beat
   docker compose --env-file .env.docker down
   ```

   **Do not use `down -v`** unless you explicitly intend to delete the PostgreSQL, Redis, and uploaded-PDF volumes.

### Authentication

Business endpoints require an `X-API-Key` request header. `/health` is intentionally public. For the examples below, supply your key locally without printing it:

```bash
read -r -s -p 'DocuRAG API key: ' DOCURAG_API_KEY; echo
```

Paste the value of `DOCURAG_API_KEY` from your **local** `.env.docker`; do not put a real key in a Git commit, screenshot, issue, or documentation example.

## API examples

**1. Upload a PDF asynchronously** (`multipart/form-data`, max 10 MiB):

```bash
curl -sS -X POST http://127.0.0.1:8000/papers/upload \
  -H "X-API-Key: $DOCURAG_API_KEY" \
  -H 'X-Request-ID: demo-upload-001' \
  -F 'file=@/path/to/your-paper.pdf;type=application/pdf'
```

A successful request returns HTTP **202** with a `document_id`, `task_id`, and `status` (typically `pending` at submission). Submission is **not** equivalent to completed parsing.

**2. Poll the processing job:**

```bash
curl -sS "http://127.0.0.1:8000/tasks/<TASK_ID>" \
  -H "X-API-Key: $DOCURAG_API_KEY"
```

Wait until `status` is `completed` before searching. Check `error_type` and worker logs if processing fails.

**3. Inspect parsed chunks and pages:**

```bash
curl -sS "http://127.0.0.1:8000/papers/<DOCUMENT_ID>/chunks" \
  -H "X-API-Key: $DOCURAG_API_KEY"
```

**4. Search the uploaded text:**

```bash
curl -sS -X POST http://127.0.0.1:8000/search \
  -H "X-API-Key: $DOCURAG_API_KEY" \
  -H 'Content-Type: application/json' \
  -H 'X-Request-ID: demo-search-001' \
  -d '{"query":"spectrogram","mode":"literal","document_id":1,"limit":5}'
```

Replace `document_id` with the value returned by your upload. Search modes currently exposed by this endpoint are `literal` and `fts`; inspect `/docs` for request details. Search results can include `document_id`, `chunk_id`, page range, content, and `retrieval_source`.

**5. Call the agent endpoint:**

```bash
curl -sS -X POST http://127.0.0.1:8000/agent/query \
  -H "X-API-Key: $DOCURAG_API_KEY" \
  -H 'Content-Type: application/json' \
  -H 'X-Request-ID: demo-agent-001' \
  -d '{"question":"What method does this paper use?"}'
```

With the default `LLM_PROVIDER=mock`, the API deliberately returns a canned final answer, with **zero tool calls and no evidence**. This checks API wiring, not genuine retrieval-based reasoning. A separate scripted-Mock harness can explicitly request registered tools and exercise the real database chain.

Additional endpoints include document CRUD, synchronous `/documents/upload`, paper metadata queries, PDF retrieval, evidence lookup, task retry, and orchestrated retrieval; refer to `/docs` for their authoritative schemas.

## Research agents and evidence guarantees

The single-turn agent exposes a whitelist of registered tools (`search_papers`, `search_chunks`, and `get_evidence`) through a bounded `ToolExecutor`. The database tool session uses a read-only transaction with a per-query statement timeout. Tool output is treated as untrusted input; IDs, page numbers, and quotations must be grounded in stored evidence rather than fabricated.

The separate multi-step LangGraph workflow supports cross-paper evidence gathering, structured extraction, exact quotation checks, evidence-matrix coverage assessment, and a bounded supplementary search round.

**Important distinction:** Exact quote matching only checks whether a proposed quotation appears in the retrieved source text. It **does not** establish that the quotation has been attributed correctly, that a claim is semantically supported, or that the final answer is accurate. PDF extraction can also have reading-order limitations, especially with multi-column papers.

### Day 12 research evaluation

A recorded evaluation used five cross-paper research questions over two database-stored papers:

| Recorded metric | Result |
|---|---:|
| Research questions | 5 |
| Tool calls | 21 |
| Verbatim quotations verified | 46 |
| Proposed quotations rejected | 8 |
| Exact quote substring-match rate | 85.2% |
| Reported model tokens | 57,074 |

These are **workflow and substring-grounding measurements**, not a validated answer-accuracy score. See [Day 12 Evaluation Report](docs/day12_report.md) for details and limitations. Real-model evaluation requires deliberately configured credentials, paper data, and an appropriate test budget.

## Testing and continuous integration

**Use the guarded test launcher rather than invoking pytest directly:**

```bash
python -m scripts.run_tests -q --tb=short
```

The launcher verifies a dedicated `docurag_test` PostgreSQL database before application/test initialization. Do not run integration tests against a development or production database. Local integration testing needs the correctly configured test database and supporting services.

The GitHub Actions workflow provisions PostgreSQL and Redis services, installs dependencies, checks syntax, runs Alembic migrations on a clean test database (including `pg_trgm` setup), and executes the suite with `LLM_PROVIDER=mock`. The latest reported workflow completed successfully. The previously reported local baseline was **466 passing tests**; the exact count may change as tests are added.

### Day 13 Docker demonstration (synthetic data)

An end-to-end engineering demonstration used a **synthetic, unpublished PDF**. Observed results:

| Check | Observed result |
|---|---|
| Async PDF submission | HTTP 202 |
| Celery job | `completed` on first attempt |
| Parsed chunks | 3, with page references |
| Literal search | HTTP 200; one hit from `postgres_literal` |
| Evidence location | Demo document 1 / chunk 1 / page 1 |
| Default HTTP Mock agent | HTTP 200; one Mock LLM call, zero tools |
| Scripted-Mock → real PostgreSQL tool | Two Mock responses, one successful `search_chunks` call |
| HTTP observability | Request ID returned and recorded in Docker JSON log |

The scripted demo lives at `evaluation/demo/run_agent_tool_demo.py`. **It assumes the Docker database already contains the synthetic demonstration document as ID 1 and the expected matching chunk as ID 1.** It is not yet a portable, fresh-install, one-command demo. With the expected data present, run it in the API container using:

```bash
docker compose --env-file .env.docker exec -T api \
  python - < evaluation/demo/run_agent_tool_demo.py
```

The synthetic PDF can be regenerated for testing; it is not an authentic scientific publication. The fixed scripted answer should not be interpreted as an independently generated or verified model conclusion.

## Security and operational limitations

- The supplied deployment binds the API to localhost and does not expose PostgreSQL or Redis ports on the host.
- `AUTH_ENABLED=true` is the intended deployment configuration. A single shared API key is **not** a multi-user identity, role, or document-ownership system; anyone with that key may access the instance's protected resources.
- Credentials belong in ignored local environment files, never version control. API keys are not embedded in this README.
- The original PDF storage must remain accessible to both the API and worker; the Compose stack shares a named upload volume.
- The database and uploaded files persist in named volumes. Backups, key rotation, rate limiting, and production deployment controls still require operational planning.
- No OCR is provided for image-only PDFs. Extracted text order and attribution need review for complex layouts.
- PostgreSQL literal/FTS search is distinct from semantic vector retrieval; embedding-based search has not been verified or delivered.
- Agent tools and exact quotes improve traceability, but do not guarantee sound research conclusions. Human verification is still needed for high-stakes or publishable findings.

## Further documentation

- [Day 12 evaluation report](docs/day12_report.md)
- [Development log](docs/development-log.md)
- Interactive API reference: <http://127.0.0.1:8000/docs> (when running locally)

## Development status

DocuRAG is an engineering and research-learning project. Its deployment, ingestion, bounded tool-chain, database retrieval, and CI have been exercised; semantic answer quality, vector retrieval, OCR, and per-user authorization remain areas for future work.
