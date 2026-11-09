# Next.js Frontend — Design Spec

**Date:** 2026-04-24
**Project:** Agentic RAG Document Intelligence API
**Replaces:** `app.py` (Streamlit frontend, step 7)

---

## Overview

Replace the Streamlit frontend with a Next.js 14 (App Router) single-page application housed in `frontend/` at the repo root. The frontend calls the FastAPI backend directly from the browser via `fetch`. Docker Compose is updated to build and serve the Next.js app instead of Streamlit.

---

## Decisions Made

| Question | Decision |
| --- | --- |
| Location | `frontend/` subfolder in this repo |
| Styling | Tailwind CSS, dark `#0F172A` bg, `#2563EB` blue accent, theme toggle |
| State management | Zustand |
| API communication | Direct browser → FastAPI (no Next.js proxy layer) |
| Docker | Full Docker Compose — Next.js service replaces Streamlit service |

---

## Project Structure

```text
frontend/
├── app/
│   ├── layout.tsx          # Root layout — fonts, ThemeProvider, global CSS
│   └── page.tsx            # Single page — renders the app shell
├── components/
│   ├── Sidebar.tsx         # Document list, upload, scope selector
│   ├── ChatWindow.tsx      # Message history + streaming output
│   ├── ChatInput.tsx       # Text input + send button
│   ├── DocumentCard.tsx    # Single document row (status badge, name, delete)
│   ├── SourcesExpander.tsx # Collapsible source citations
│   └── ThemeToggle.tsx     # Dark/light toggle button
├── lib/
│   ├── api.ts              # Typed fetch wrappers for all FastAPI endpoints
│   └── store.ts            # Zustand store
├── types/
│   └── index.ts            # TypeScript types mirroring API schemas
├── .env.local              # NEXT_PUBLIC_API_URL=http://localhost:8000
├── next.config.ts
├── tailwind.config.ts
└── package.json
```

---

## Zustand Store

```ts
interface AppState {
  // Chat
  messages: Message[]           // { id, role, content, sources? }
  sessionId: string             // UUID generated once on app load
  isStreaming: boolean          // true while SSE connection is open

  // Documents
  documents: DocumentStatus[]   // mirrors GET /documents
  selectedDocId: string | null  // null = query all documents
  isPolling: boolean            // true while any doc is "processing"

  // Theme
  theme: "dark" | "light"
}
```

---

## TypeScript Types (`types/index.ts`)

Mirror the FastAPI Pydantic schemas exactly:

```ts
export interface DocumentStatus {
  doc_id: string
  filename: string
  status: "processing" | "ready" | "failed"
  error?: string
  created_at: string
  chunk_count?: number
}

export interface SourceChunk {
  doc_id: string
  filename: string
  page_number?: number
  text: string
  score: number
}

export interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  sources?: SourceChunk[]
}
```

---

## API Client (`lib/api.ts`)

Typed wrappers for every backend endpoint:

- `fetchDocuments(): Promise<DocumentStatus[]>` — GET /documents
- `uploadDocument(file: File): Promise<UploadResponse>` — POST /upload
- `deleteDocument(docId: string): Promise<void>` — DELETE /documents/{doc_id}
- `streamAnswer(payload, onToken, onSources, onDone, onError)` — POST /ask/stream, parses SSE with native `fetch` + `ReadableStream`

SSE parsing reads the response body as a `ReadableStream`, splits on `\n\n`, strips the `data:` prefix, and dispatches to the appropriate callback by `event.type`.

---

## Chat Streaming Data Flow

1. User submits question → `ChatInput` calls store `sendMessage(question)`
2. Store appends `{ role: "user", content: question }` to messages
3. Store appends `{ role: "assistant", content: "" }` placeholder, sets `isStreaming: true`
4. `api.ts` opens `fetch` POST to `/ask/stream`
5. Each `token` event: append delta to last message's `content` (in-place Zustand update)
6. `sources` event: attach `SourceChunk[]` to last message
7. `done` event: set `isStreaming: false`
8. `error` event: replace placeholder content with error text, set `isStreaming: false`
9. `ChatWindow` re-renders on each store update — shows streaming cursor `▌` while `isStreaming`

---

## Document Polling

After any upload, start `setInterval(fetchDocuments, 2000)`. On each tick, update `documents` in the store. When no document has `status: "processing"`, clear the interval and set `isPolling: false`.

This is non-blocking — the UI stays fully interactive during ingestion, replacing the `time.sleep() + st.rerun()` pattern from Streamlit.

---

## Error Handling

| Scenario | Behaviour |
| --- | --- |
| API unreachable | Inline error in chat: "Cannot reach API at `{url}`. Is the server running?" |
| Upload fails | Error banner in sidebar below the upload zone |
| Document ingestion fails | `DocumentCard` shows red badge + error tooltip |
| SSE `error` event | Replaces streaming placeholder with error text |
| HTTP 4xx/5xx from `/ask/stream` | Error shown inline in chat |

---

## Design Tokens

```css
/* Dark (default) */
--bg:       #0F172A;
--surface:  #1E293B;
--text:     #F1F5F9;
--accent:   #3B82F6;
--success:  #34D399;
--error:    #F87171;

/* Light */
--bg:       #FFFFFF;
--surface:  #F8FAFB;
--text:     #1F2937;
--accent:   #2563EB;
--success:  #10B981;
--error:    #EF4444;
```

Theme toggle stored in Zustand + `localStorage` (persisted via `zustand/middleware` `persist`).

---

## Layout

Single-page layout — sidebar on the left, chat on the right:

```text
┌─────────────────┬────────────────────────────────────┐
│  Sidebar        │  Chat Window                       │
│                 │                                    │
│  [Upload zone]  │  [message bubbles]                 │
│  ─────────────  │  [streaming message + cursor]      │
│  Doc 1 🟢  [✕] │                                    │
│  Doc 2 🟡  [✕] │                                    │
│  Doc 3 🔴  [✕] │                                    │
│  ─────────────  │                                    │
│  Scope: [All ▾] │                                    │
│  ─────────────  │                                    │
│  [Clear chat]   │  [chat input________________] [→]  │
│  [Theme toggle] │                                    │
└─────────────────┴────────────────────────────────────┘
```

---

## Docker Changes

### `docker-compose.yml` — replace `frontend` service

```yaml
frontend:
  build:
    context: ./frontend
    dockerfile: Dockerfile
  container_name: rag-frontend
  depends_on:
    api:
      condition: service_healthy
  ports:
    - "3000:3000"
  environment:
    NEXT_PUBLIC_API_URL: http://localhost:8000
  restart: unless-stopped
```

### `frontend/Dockerfile`

Two-stage build:

1. `node:20-alpine` — install deps, run `next build`
2. Same image — run `next start` on port 3000

### CORS update

`main.py` reads `CORS_ORIGINS` from the environment — no source code change needed. Update two places:

- `.env.example`: change default to `http://localhost:3000,http://localhost:8501`
- `docker-compose.yml` `api` service env: set `CORS_ORIGINS: http://localhost:3000`

---

## Files to Delete

These are backed up on GitHub and no longer needed:

- `app.py` — Streamlit frontend, replaced by Next.js

---

## Out of Scope

- Backend changes beyond the CORS env var update
- Authentication / user accounts
- Persistent chat history (in-memory session state is unchanged)
- Redis / Postgres state (documented as v2 work in CLAUDE.md)
