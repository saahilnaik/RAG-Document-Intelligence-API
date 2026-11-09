# Agentic RAG Document Intelligence API

A production-shaped **Retrieval-Augmented Generation (RAG)** service. Upload PDF, DOCX, TXT or Markdown files, ask questions in natural language, and get **cited answers** with real-time streaming and per-session conversational memory.

**Stack is 100% free**: the only signup is a free [Groq API key](https://console.groq.com). Embeddings and reranking run locally on CPU.

## Highlights

- **Hybrid retrieval**: semantic search (Chroma) + BM25 keyword search, fused with Reciprocal Rank Fusion, then reranked by a cross-encoder and filtered by a relevance threshold.
- **Cited answers**: every answer cites `[filename:page]`. Citations that match no retrieved chunk are reported as `unverified_citations`.
- **No-answer guard**: if no chunk is relevant enough, the API replies "couldn't find anything" without calling the LLM.
- **Streaming**: tokens arrive over Server-Sent Events; conversation memory per `session_id`.
- **Multi-tenant**: API-key auth (`X-API-Key`), all data scoped per user, per-user document limits.
- **Resilient LLM calls**: timeouts, retries and an automatic fallback model.
- **Quality gate**: RAGAS scoring via `/evaluate` or CLI, enforced in CI.
- **Production plumbing**: Postgres registry, Redis sessions + ARQ ingestion worker, Chroma server, Caddy HTTPS, health/readiness probes, Prometheus metrics, JSON logs, optional Sentry.
- **Next.js 14 chat UI** with streaming, citations and dark/light mode.

## Architecture

```
Browser (Next.js 14)
   │  HTTPS
   ▼
Caddy  ── /v1/*  ──►  FastAPI (api)  ──►  Groq (Llama 3.3 70B)
   │                     │   │
   └── /  ──► frontend   │   ├──► Postgres  (document registry)
                         │   ├──► Redis     (sessions + ingestion queue)
                         │   └──► Chroma    (vectors, server mode)
                         ▼
                   ARQ worker (ingestion): extract → chunk → embed → store
```

Without `DATABASE_URL` / `REDIS_URL` / `CHROMA_HOST` everything falls back to in-process backends (embedded Chroma, in-memory registry and sessions, FastAPI `BackgroundTasks`), which is what local development uses.

### Ingestion

```
POST /v1/upload
  → validate type/size, enforce per-user doc limit, save file, register doc
  → background task or queued ARQ job:
      extract_text() → chunk (1000 chars / 200 overlap) → embed (BAAI/bge-small-en-v1.5)
      → store in Chroma with {doc_id, filename, page_number, file_type} → mark ready
```

### Query

```
POST /v1/ask or /v1/ask/stream
  → load session history → condense follow-up into a standalone question
  → retrieve: semantic + BM25 → RRF fusion → cross-encoder rerank → drop low scores
  → (nothing relevant? fixed "not found" answer, no LLM call)
  → generate cited answer with ChatGroq → verify citations → save turn to memory
```

## Tech stack

| Layer | Technology |
|---|---|
| API | FastAPI, Uvicorn / Gunicorn |
| LLM | Groq `llama-3.3-70b-versatile` (fallback `llama-3.1-8b-instant`) |
| Embeddings | `BAAI/bge-small-en-v1.5` (local, 384-dim) |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` (local) |
| Vector store | ChromaDB (embedded or server mode) |
| Orchestration | LangChain 1.x (LCEL) |
| Shared state | Postgres (SQLAlchemy), Redis, ARQ |
| Evaluation | RAGAS |
| Frontend | Next.js 14, React 18, TypeScript, Zustand, Tailwind CSS |
| Edge / infra | Docker Compose, Caddy |
| Quality | pytest, Vitest + React Testing Library, ruff, pre-commit, GitHub Actions |

## Quick start (local development)

Prerequisites: Python 3.11, Node.js 20+, a free [Groq API key](https://console.groq.com).

```bash
git clone https://github.com/saahilnaik9/rag-document-intelligence-api
cd rag-document-intelligence-api

# Backend
py -3.11 -m venv venv
venv\Scripts\pip install -r requirements.txt
copy .env.example .env          # then set GROQ_API_KEY

# Frontend
cd frontend && npm install && cd ..
```

Run both servers (two terminals):

```bash
venv\Scripts\uvicorn main:app --reload      # API  → http://localhost:8000 (Swagger at /docs)
cd frontend && npm run dev                  # UI   → http://localhost:3000
```

For quick local use, set `AUTH_ENABLED=false` in `.env`. Otherwise set `API_KEYS` (see [Authentication](#authentication)) and put one of the keys in `frontend/.env.local` as `NEXT_PUBLIC_API_KEY`.

The first upload downloads the embedding model (~130 MB) and the reranker.

## Docker (full stack)

```bash
copy .env.example .env
# set GROQ_API_KEY, POSTGRES_PASSWORD and API_KEYS in .env
docker compose up --build
```

| Service | Notes |
|---|---|
| `caddy` | Only published ports (80/443). Frontend at `/`, API at `/v1/*`. HTTPS via `DOMAIN` (defaults to a local cert for `localhost`). |
| `api` | FastAPI behind Caddy; healthcheck on `/readyz`. |
| `worker` | ARQ ingestion worker. Scale with `docker compose up --scale worker=N`. |
| `postgres`, `redis`, `chroma` | Document registry, sessions/queue, vectors (persistent volumes). |
| `frontend` | Next.js; waits for the API to be ready. |

Open **https://localhost**. `/metrics`, `/readyz` and the unversioned routes are deliberately not exposed through Caddy. Set `PUBLIC_URL` and `NEXT_PUBLIC_API_KEY` at build time for a real deployment.

## Authentication

Every endpoint except the health probes requires an `X-API-Key` header when `AUTH_ENABLED=true` (the default). Keys map to user ids:

```env
API_KEYS={"<generated-key>": "alice"}
```

Generate a key with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Documents, sessions and queries are isolated per user. `NEXT_PUBLIC_API_KEY` is visible to the browser, so use it for demos only.

## API reference

Use the versioned `/v1` prefix (unprefixed routes remain for older clients). Interactive docs: `/docs`.

| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/upload` | Upload a file (`multipart/form-data`, field `file`). Returns `202 {doc_id, filename, status: "processing"}`. `429` when the per-user document limit is reached. |
| `GET` | `/v1/documents` | List your documents. |
| `GET` | `/v1/documents/{doc_id}` | `{doc_id, filename, status, chunk_count, error, created_at}`; status is `processing`, `ready` or `failed`. |
| `DELETE` | `/v1/documents/{doc_id}` | Remove from the vector store and registry (`204`). |
| `POST` | `/v1/ask` | Non-streaming answer. |
| `POST` | `/v1/ask/stream` | Streaming answer over SSE. |
| `POST` | `/v1/evaluate` | RAGAS scores for a question/answer/contexts triple. |
| `GET` | `/healthz` | Liveness (never touches dependencies). |
| `GET` | `/readyz` | Readiness: `200`, or `503` if a configured dependency is down. |
| `GET` | `/metrics` | Prometheus metrics (internal only). |

### Ask

```http
POST /v1/ask
X-API-Key: <key>
Content-Type: application/json

{
  "question": "What are the main findings?",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "doc_id": "optional-uuid-to-scope-search"
}
```

Response:

```json
{
  "answer": "… [report.pdf:3]",
  "sources": [{"doc_id": "…", "filename": "report.pdf", "page_number": 3, "text": "…", "score": 0.92}],
  "session_id": "550e8400-…",
  "unverified_citations": []
}
```

`/v1/ask/stream` takes the same body and emits `data: {json}\n\n` events:

| Event | Meaning |
|---|---|
| `token` | A streamed piece of the answer. |
| `citations` | Sent only if the answer cites something that matches no retrieved chunk: `{"unverified": [...]}`. |
| `sources` | Final citations, sent once. |
| `done` | Stream finished. |
| `error` | Generation failed. |

### Evaluate

```http
POST /v1/evaluate
{ "question": "…", "answer": "…", "contexts": ["chunk 1", "chunk 2"], "ground_truth": "optional" }
```

Returns `faithfulness`, `answer_relevancy` and (when `ground_truth` is given) `context_precision`, each 0–1.

## Quality evaluation (RAGAS)

| Metric | Measures |
|---|---|
| Faithfulness | Is the answer grounded in the retrieved context? |
| Answer relevancy | Does the answer address the question? |
| Context precision | Are the retrieved chunks relevant? (needs ground truth) |

```bash
# Batch evaluation (JSONL lines: {"question": "...", "ground_truth": "..."})
venv\Scripts\python scripts/evaluate.py eval_dataset/sample_qa.jsonl
# → metrics table + eval_results/{timestamp}.json

# Scope to one document
venv\Scripts\python scripts/evaluate.py eval_dataset/sample_qa.jsonl --doc-id <uuid>

# Ingest a file first and fail if quality drops (this is what CI runs)
venv\Scripts\python scripts/evaluate.py eval_dataset/sample_qa.jsonl \
  --ingest eval_dataset/sample.pdf --fail-under faithfulness=0.70 answer_relevancy=0.60
```

## Testing and linting

```bash
venv\Scripts\pytest tests/ -v                       # backend (no API keys or network needed)
venv\Scripts\pytest tests/test_routes.py -v         # a single file
venv\Scripts\ruff check .                           # lint
cd frontend && npm test && npm run lint             # frontend
```

CI (`.github/workflows/ci.yml`) runs backend lint + tests, dependency audit, frontend lint/test/build, Docker image builds with a Trivy scan and compose validation, and a weekly RAGAS quality gate on `main`. Install the pre-commit hooks with `pre-commit install`.

## Configuration

All settings live in `core/config.py` and are read from `.env` (see `.env.example`).

| Group | Variables (defaults) |
|---|---|
| LLM | `GROQ_API_KEY` (**required**), `GROQ_CHAT_MODEL` (`llama-3.3-70b-versatile`), `GROQ_FALLBACK_MODEL` (`llama-3.1-8b-instant`, empty disables), `LLM_TEMPERATURE` (0.0), `LLM_MAX_TOKENS` (1024), `LLM_TIMEOUT_SECONDS` (60), `LLM_MAX_RETRIES` (3) |
| Embeddings | `EMBEDDING_MODEL` (`BAAI/bge-small-en-v1.5`), `EMBEDDING_DEVICE` (`cpu`) |
| Retrieval | `RETRIEVAL_K` (5), `HYBRID_ENABLED` (true), `RETRIEVAL_CANDIDATES` (20), `RERANK_ENABLED` (true), `RERANKER_MODEL`, `MIN_RELEVANCE_SCORE` (0.01) |
| Chunking / memory | `CHUNK_SIZE` (1000), `CHUNK_OVERLAP` (200), `MAX_CONVERSATION_TURNS` (5), `SESSION_TTL_SECONDS` (86400) |
| Storage | `CHROMA_PERSIST_DIR` (`./data/chroma`), `CHROMA_COLLECTION`, `UPLOAD_DIR` (`./data/uploads`), `MAX_UPLOAD_SIZE_MB` (25) |
| Auth / limits | `AUTH_ENABLED` (true), `API_KEYS`, `MAX_DOCS_PER_USER` (50), `MAX_QUESTION_CHARS` (2000), `CORS_ORIGINS` |
| Shared state | `DATABASE_URL`, `REDIS_URL`, `CHROMA_HOST`, `CHROMA_PORT`, `INGEST_MAX_TRIES` (3), `INGEST_STALE_MINUTES` (30) |
| Observability | `ENVIRONMENT`, `LOG_FORMAT` (`text`, use `json` in containers), `LOG_LEVEL`, `SENTRY_DSN` |
| Docker / frontend | `POSTGRES_PASSWORD`, `DOMAIN`, `PUBLIC_URL`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_API_KEY` |

## Project layout

```
.
├── main.py                 FastAPI app, lifespan, CORS, health endpoints
├── worker.py               ARQ ingestion worker
├── gunicorn.conf.py        Production server config
├── api/                    Routes and Pydantic schemas
├── core/                   Config, auth, health, logging, observability, upload checks
├── services/
│   ├── qa.py               LCEL chain (get_answer / astream_answer)
│   ├── retrieval.py        Hybrid retrieval + RRF + threshold
│   ├── bm25.py             Keyword index
│   ├── reranker.py         Cross-encoder rerank
│   ├── citations.py        Citation verification
│   ├── document_processor.py / ingestion.py / vector_store.py
│   ├── document_registry.py / session_memory.py / job_queue.py
│   └── evaluation.py / eval_gate.py
├── scripts/evaluate.py     RAGAS CLI and quality gate
├── eval_dataset/           Sample PDF and Q&A pairs
├── tests/                  pytest suite
├── frontend/               Next.js 14 app (app/, components/, lib/, __tests__/)
├── Dockerfile, docker-compose.yml, Caddyfile
└── .github/workflows/ci.yml
```

## Design notes

- **Local embeddings**: zero API cost; the Docker build pre-downloads the model so containers start fast.
- **One Chroma collection with `doc_id` metadata filters**: cross-document queries need no filter, single-document queries filter on `doc_id`, and deletion is `delete(where={"doc_id": …})`.
- **LCEL over `ConversationalRetrievalChain`**: `create_history_aware_retriever` + `create_retrieval_chain` stream per-token deltas that map directly to SSE.
- **Lazy initialization**: settings, models and backends are created on first use, so the app starts even with missing env vars and errors surface at request time.
- **Pluggable shared state**: Postgres/Redis/Chroma-server are opt-in via env vars; the in-process fallbacks keep local dev and tests dependency-free. A separate worker requires `CHROMA_HOST`, because embedded Chroma is single-process.

## Troubleshooting

- **Answers say nothing was found**: check `GET /v1/documents/{doc_id}` shows `ready`; try lowering `MIN_RELEVANCE_SCORE` (with the reranker off, scores are cosine similarity and ~0.3 is a sensible value); re-upload if the data directory was cleared.
- **Slow first request**: the embedding and reranker models download on first use.
- **401**: send `X-API-Key` with a key from `API_KEYS`, or set `AUTH_ENABLED=false` for local use.
- **`docker compose` fails on startup**: `API_KEYS` and `POSTGRES_PASSWORD` must be set in `.env`.
- **Port in use**: `netstat -ano | findstr :8000`, then `taskkill /PID <PID> /F`.

## Resources

[LangChain](https://python.langchain.com) · [ChromaDB](https://docs.trychroma.com) · [RAGAS](https://docs.ragas.io) · [Groq](https://console.groq.com) · [BGE embeddings](https://huggingface.co/BAAI/bge-small-en-v1.5) · [FastAPI](https://fastapi.tiangolo.com) · [Next.js](https://nextjs.org)

Issues and feature requests: [GitHub](https://github.com/saahilnaik9/rag-document-intelligence-api).
