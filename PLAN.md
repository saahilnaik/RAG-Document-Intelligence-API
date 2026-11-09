# PLAN.md — Agentic RAG Document Intelligence API

> In-repo implementation roadmap. For architecture + commands see [CLAUDE.md](CLAUDE.md). For the deep design rationale see `C:\Users\sahil\.claude\plans\project-agentic-rag-tranquil-spring.md`.

## Goal

Ship a production-shaped, **100% free-tier** RAG REST API:

- Upload PDFs / DOCX / TXT → chunk → embed locally → store in ChromaDB
- Ask questions via `/ask` (JSON) or `/ask/stream` (SSE) — answers cite `[filename:page]`
- Per-`session_id` conversational memory (last 5 turns)
- Self-evaluate with RAGAS (faithfulness, answer_relevancy, context_precision) via both a CLI and a `/evaluate` endpoint
- Streamlit chat UI alongside the API
- One-command Docker spin-up

Target reviewer: a hiring manager opening the repo. Every decision should pay rent as either production signal or interview-story signal.

## Stack

| Layer | Choice | Why |
|---|---|---|
| LLM | **Groq `llama-3.3-70b-versatile`** | Free tier, ~500 tok/s, real cloud API |
| Embeddings | **`BAAI/bge-small-en-v1.5`** (local) | Free, 384-dim, strong MTEB scores, no API key |
| Vector store | **ChromaDB** (local persistent) | Free, metadata-filtered per `doc_id` |
| Framework | FastAPI + Pydantic v2 | Production default |
| Chains | LangChain 1.x **LCEL** | Streams cleanly; avoid deprecated `ConversationalRetrievalChain` |
| Judge (RAGAS) | Same Groq + HF embeddings | Free eval too |
| Frontend | Streamlit | Fast demo surface |
| Container | Docker + docker-compose | One-command spin-up |

**Only external signup:** free Groq account.

## File layout

```
.
├── CLAUDE.md                     Claude Code project instructions
├── PLAN.md                       this file
├── README.md                     interview-ready narrative (step 9)
├── main.py                       FastAPI app, lifespan, CORS, router mount
├── app.py                        Streamlit frontend
├── api/
│   ├── routes.py                 /upload, /ask, /ask/stream, /documents*, /evaluate, /health
│   └── schemas.py                Pydantic models
├── core/
│   ├── config.py                 Settings + @lru_cache
│   └── logging.py                structlog JSON logs
├── services/
│   ├── document_processor.py     extract_text + chunk_documents
│   ├── vector_store.py           VectorStoreManager (Chroma + BGE)
│   ├── qa.py                     get_answer + astream_answer + _ManagerRetriever
│   ├── evaluation.py             RAGAS wrapper
│   ├── document_registry.py      in-memory (threading.Lock)
│   └── session_memory.py         in-memory (threading.Lock)
├── scripts/
│   └── evaluate.py               CLI batch evaluator
├── tests/
│   ├── conftest.py               mocks + TestClient + autouse reset
│   ├── test_routes.py
│   ├── test_document_processor.py
│   ├── test_session_memory.py
│   └── test_evaluation.py
├── data/                         gitignored; runtime only
│   ├── uploads/
│   └── chroma/
├── eval_dataset/
│   ├── sample.pdf                seed demo PDF
│   └── sample_qa.jsonl           ground-truth Q/A for RAGAS
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .env.example
└── .gitignore
```

## Implementation order

Each step must be green (tests pass + manual smoke test) before the next.

### Step 0 — Contract files _(done)_
- [x] `CLAUDE.md`
- [x] `PLAN.md`

### Step 1 — Scaffolding _(done)_

- [x] `requirements.txt`
- [x] `.env.example`, `.gitignore`, `.dockerignore`
- [x] `core/config.py` (Settings + `@lru_cache get_settings()`)
- [x] `core/logging.py` (structlog setup)
- [x] `main.py` stub with `GET /health` and CORS middleware
- [x] Verify `uvicorn main:app --reload` boots and `/health` returns 200

### Step 2 — Schemas + registries _(done)_

- [x] `api/schemas.py` (all Pydantic models from design)
- [x] `services/document_registry.py`
- [x] `services/session_memory.py`
- [x] `tests/conftest.py` with dummy env vars + autouse `_reset_registries`
- [x] `tests/test_session_memory.py` — eviction + isolation

### Step 3 — Ingestion _(done)_

- [x] `services/document_processor.py` (extract_text + chunk_documents)
- [x] `services/vector_store.py` (`VectorStoreManager`, lazy init, metadata filter)
- [x] `api/routes.py`: `POST /upload`, `GET /documents`, `GET /documents/{id}`, `DELETE /documents/{id}`
- [x] `_ingest_document` BackgroundTask wires extract → chunk → store → mark_ready
- [x] `tests/test_document_processor.py` — metadata preservation
- [x] `tests/test_routes.py` — upload happy + invalid cases (mocked vector store)
- [x] **Smoke**: upload real PDF → status goes `processing` → `ready`

### Step 4 — QA (non-streaming) _(done)_

- [x] `services/qa.py`: `_ManagerRetriever`, `get_answer`, LCEL chain with `ChatGroq`
- [x] `api/routes.py`: `POST /ask` (409 if processing, 404 if unknown)
- [x] `tests/test_routes.py` — `/ask` with mocked qa
- [x] **Smoke**: upload PDF, ask question, get cited answer

### Step 5 — QA (streaming) _(done)_

- [x] `services/qa.py`: `astream_answer` yielding `token` / `sources` / `done` / `error` events
- [x] `api/routes.py`: `POST /ask/stream` → `StreamingResponse(media_type="text/event-stream")`
- [x] `tests/test_routes.py` — SSE chunks via `client.stream`
- [x] **Smoke**: `curl -N` sees tokens arrive live

### Step 6 — Evaluation _(done)_

- [x] `services/evaluation.py` (`score_single`, `score_batch` with Groq judge + HF embeddings)
- [x] `api/routes.py`: `POST /evaluate`
- [x] `scripts/evaluate.py` CLI (reads JSONL, runs real pipeline, prints table, writes JSON)
- [x] `eval_dataset/sample.pdf` + `eval_dataset/sample_qa.jsonl` (~5 pairs)
- [x] `tests/test_evaluation.py` — `score_single` shape with mocked RAGAS

### Step 7 — Streamlit frontend _(done)_

- [x] `app.py`: sidebar uploader + doc list polling, main chat with streaming token render, source expander
- [x] **Smoke**: full upload + streaming chat flow in browser

### Step 8 — Docker

- [ ] `Dockerfile` (python:3.11-slim, pre-download BGE in build step)
- [ ] `docker-compose.yml` (api + frontend services, named volume for `/app/data`)
- [ ] **Smoke**: cold `docker compose up --build`, hit both URLs, restart and confirm data persists

### Step 9 — README polish

- [ ] Problem statement
- [ ] Mermaid architecture diagram
- [ ] Quickstart (`docker compose up`)
- [ ] `curl` examples for every endpoint
- [ ] Design decisions (why Groq, why BGE, why LCEL, why metadata-filter)
- [ ] RAGAS sample output
- [ ] Roadmap (reranking, Redis, auth, Claude/GPT swap)

## Verification checklist (after Step 9)

```bash
# 1. Unit tests
venv\Scripts\pytest tests/ -v                         # all green

# 2. API boot + Swagger UI
venv\Scripts\uvicorn main:app --reload                # http://localhost:8000/docs

# 3. Ingest seed PDF → poll /documents/{id} until ready
# 4. POST /ask (non-streaming) → answer + sources
# 5. POST /ask/stream via curl -N → live token frames
# 6. Follow-up question on same session_id → references prior turn
# 7. python scripts/evaluate.py → metrics table + JSON output
# 8. POST /evaluate → scores a single query
# 9. streamlit run app.py → full upload + streaming chat in browser
# 10. docker compose up --build → both services up, data persists across restart
```

## Out of scope (v1)

- Reranking stage (deferred)
- Redis/Postgres for registries + memory (v2)
- Auth / rate limiting
- Claude/GPT integration (LangChain abstraction makes it a one-line swap later)
- GPU embedding inference

## Known risks

- **LangChain 1.x churn** — verify `create_history_aware_retriever` import path at implementation time
- **BGE cold start** — ~130 MB first download; pre-download in Dockerfile build step
- **Groq rate limits** — 30 RPM; RAGAS batch eval may need backoff between calls
- **RAGAS + non-OpenAI judge** — pin `ragas` to a known-good release
- **SSE behind proxies** — locally fine; prod needs `proxy_buffering off` on nginx