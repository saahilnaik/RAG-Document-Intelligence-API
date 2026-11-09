# Next.js Frontend (Path B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `app.py` (Streamlit) with a Next.js 14 App Router frontend in `frontend/` that connects directly to the FastAPI backend at `http://localhost:8000`.

**Architecture:** Single-page Next.js app, all client components, Zustand for shared state (chat messages, documents, session, theme). Browser calls FastAPI directly via `fetch`. SSE streaming parsed with native `ReadableStream`. Document polling via `setInterval`, non-blocking.

**Tech Stack:** Next.js 14 (App Router), TypeScript, Tailwind CSS (`darkMode: 'class'`), Zustand, Vitest + React Testing Library

---

## File Map

**Create:**
- `frontend/` — entire Next.js project (scaffolded via `create-next-app` in Task 1)
- `frontend/next.config.ts` — enables `output: 'standalone'` for Docker
- `frontend/tailwind.config.ts` — enables dark mode, maps design token colors
- `frontend/vitest.config.ts` — test runner config
- `frontend/vitest.setup.ts` — jest-dom matchers
- `frontend/.env.local` — `NEXT_PUBLIC_API_URL=http://localhost:8000`
- `frontend/app/globals.css` — Tailwind directives + CSS variable design tokens
- `frontend/app/layout.tsx` — root HTML shell, renders `<ThemeProvider>`
- `frontend/app/page.tsx` — main page: `<Sidebar>` + `<ChatWindow>` + `<ChatInput>`
- `frontend/types/index.ts` — TypeScript interfaces mirroring FastAPI schemas
- `frontend/lib/store.ts` — Zustand store (state + mutations only, no API calls)
- `frontend/lib/api.ts` — typed fetch wrappers for all FastAPI endpoints
- `frontend/lib/useChat.ts` — custom hook: orchestrates streaming call + dispatches to store
- `frontend/components/ThemeProvider.tsx` — applies/removes `dark` class on `<html>`
- `frontend/components/ThemeToggle.tsx` — dark/light toggle button
- `frontend/components/DocumentCard.tsx` — single doc row: status badge, filename, delete button
- `frontend/components/SourcesExpander.tsx` — collapsible list of `SourceChunk` citations
- `frontend/components/Sidebar.tsx` — upload zone, document list, scope selector, clear chat
- `frontend/components/ChatInput.tsx` — textarea + send button, disabled while streaming
- `frontend/components/ChatWindow.tsx` — message history, streaming cursor, sources
- `frontend/Dockerfile` — two-stage build: `node:20-alpine` build → standalone run
- `frontend/__tests__/store.test.ts` — store action tests
- `frontend/__tests__/api.test.ts` — fetch wrapper tests (mocked `fetch`)
- `frontend/__tests__/components.test.tsx` — component smoke + behavior tests

**Modify:**
- `docker-compose.yml` — replace Streamlit `frontend` service with Next.js service
- `.env.example` — add `http://localhost:3000` to `CORS_ORIGINS` default

**Delete:**
- `app.py`

---

### Task 1: Scaffold Next.js project and install dependencies

**Files:**
- Create: `frontend/` (via `create-next-app`)
- Modify: `frontend/package.json` (add extra scripts + deps)

- [ ] **Step 1: Verify Node.js ≥ 18.17 is available**

Run in a terminal where Node.js is installed (Windows Terminal, PowerShell, or CMD — not Git Bash if `node` is absent there):

```bash
node --version
```

Expected: `v18.x.x` or higher. If not installed, download from https://nodejs.org/en/download (LTS).

- [ ] **Step 2: Scaffold the project**

From the repo root (the `Agentic RAG Document Intelligence API` directory):

```bash
npx create-next-app@14 frontend \
  --typescript \
  --tailwind \
  --eslint \
  --app \
  --no-src-dir \
  --import-alias "@/*" \
  --no-git
```

When prompted "Would you like to use Turbopack for next dev?", answer **No**.

Expected: `frontend/` directory created with `app/`, `public/`, `package.json`, `tsconfig.json`, `tailwind.config.ts`, `next.config.ts`.

- [ ] **Step 3: Install runtime dependencies**

```bash
cd frontend && npm install zustand
```

- [ ] **Step 4: Install test dependencies**

```bash
npm install -D vitest @vitejs/plugin-react @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom @types/node
```

- [ ] **Step 5: Add test script to package.json**

Open `frontend/package.json`. In the `"scripts"` block, add these two lines (keep the existing scripts):

```json
"test": "vitest run",
"test:watch": "vitest"
```

- [ ] **Step 6: Delete create-next-app boilerplate you will not use**

```bash
rm -rf frontend/public/next.svg frontend/public/vercel.svg
```

- [ ] **Step 7: Commit scaffold**

```bash
cd ..
git add frontend/
git commit -m "chore: scaffold Next.js 14 frontend with deps"
```

---

### Task 2: Configure Tailwind dark mode and design tokens

**Files:**
- Modify: `frontend/tailwind.config.ts`
- Modify: `frontend/app/globals.css`

- [ ] **Step 1: Replace `frontend/tailwind.config.ts`**

```ts
import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: 'class',
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
export default config
```

- [ ] **Step 2: Replace `frontend/app/globals.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  /* Light mode tokens */
  --bg: #ffffff;
  --surface: #f8fafb;
  --fg: #1f2937;
  --accent: #2563eb;
  --success: #10b981;
  --error: #ef4444;
  --border: #e5e7eb;
}

.dark {
  /* Dark mode tokens */
  --bg: #0f172a;
  --surface: #1e293b;
  --fg: #f1f5f9;
  --accent: #3b82f6;
  --success: #34d399;
  --error: #f87171;
  --border: #334155;
}

* {
  box-sizing: border-box;
}

html,
body {
  height: 100%;
  background-color: var(--bg);
  color: var(--fg);
}

#__next,
main {
  height: 100%;
}
```

- [ ] **Step 3: Verify Tailwind picks up the config**

```bash
cd frontend && npm run build 2>&1 | head -20
```

Expected: build completes without Tailwind errors (warnings about unused CSS are fine).

- [ ] **Step 4: Commit**

```bash
cd ..
git add frontend/tailwind.config.ts frontend/app/globals.css
git commit -m "style: configure Tailwind dark mode and CSS design tokens"
```

---

### Task 3: Set up Vitest test infrastructure

**Files:**
- Create: `frontend/vitest.config.ts`
- Create: `frontend/vitest.setup.ts`

- [ ] **Step 1: Create `frontend/vitest.config.ts`**

```ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    globals: true,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, '.'),
    },
  },
})
```

- [ ] **Step 2: Create `frontend/vitest.setup.ts`**

```ts
import '@testing-library/jest-dom'
```

- [ ] **Step 3: Write a smoke test to verify the setup works**

Create `frontend/__tests__/setup.test.ts`:

```ts
import { describe, it, expect } from 'vitest'

describe('vitest setup', () => {
  it('runs a test', () => {
    expect(1 + 1).toBe(2)
  })
})
```

- [ ] **Step 4: Run the smoke test**

```bash
cd frontend && npm test
```

Expected output:
```
✓ __tests__/setup.test.ts (1)
  ✓ vitest setup > runs a test

Test Files  1 passed (1)
Tests       1 passed (1)
```

- [ ] **Step 5: Delete the smoke test and commit**

```bash
rm __tests__/setup.test.ts
cd ..
git add frontend/vitest.config.ts frontend/vitest.setup.ts frontend/package.json
git commit -m "test: configure Vitest + React Testing Library"
```

---

### Task 4: TypeScript types

**Files:**
- Create: `frontend/types/index.ts`

No tests needed — these are compile-time contracts that will be validated by TypeScript throughout the plan.

- [ ] **Step 1: Create `frontend/types/index.ts`**

```ts
export interface DocumentStatus {
  doc_id: string
  filename: string
  status: 'processing' | 'ready' | 'failed'
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
  role: 'user' | 'assistant'
  content: string
  sources?: SourceChunk[]
}

export interface UploadResponse {
  doc_id: string
  filename: string
  status: 'processing'
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd ..
git add frontend/types/index.ts
git commit -m "feat: add TypeScript types mirroring FastAPI schemas"
```

---

### Task 5: Zustand store (TDD)

**Files:**
- Create: `frontend/__tests__/store.test.ts`
- Create: `frontend/lib/store.ts`

- [ ] **Step 1: Write the failing tests**

Create `frontend/__tests__/store.test.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { useAppStore } from '@/lib/store'
import type { DocumentStatus, SourceChunk } from '@/types'

const resetStore = () =>
  useAppStore.setState({
    messages: [],
    sessionId: 'test-session',
    isStreaming: false,
    documents: [],
    selectedDocId: null,
    isPolling: false,
    theme: 'dark',
  })

beforeEach(resetStore)

describe('addMessage', () => {
  it('appends a user message', () => {
    useAppStore.getState().addMessage({ id: '1', role: 'user', content: 'hello' })
    expect(useAppStore.getState().messages).toHaveLength(1)
    expect(useAppStore.getState().messages[0].content).toBe('hello')
  })
})

describe('appendToken', () => {
  it('appends a token to the last assistant message', () => {
    useAppStore.getState().addMessage({ id: '1', role: 'assistant', content: '' })
    useAppStore.getState().appendToken('Hi')
    useAppStore.getState().appendToken('!')
    expect(useAppStore.getState().messages[0].content).toBe('Hi!')
  })

  it('does not modify user messages', () => {
    useAppStore.getState().addMessage({ id: '1', role: 'user', content: 'question' })
    useAppStore.getState().appendToken('ignored')
    expect(useAppStore.getState().messages[0].content).toBe('question')
  })
})

describe('setMessageSources', () => {
  it('attaches sources to the correct message by id', () => {
    useAppStore.getState().addMessage({ id: 'msg-1', role: 'assistant', content: 'answer' })
    const sources: SourceChunk[] = [
      { doc_id: 'd1', filename: 'a.pdf', text: 'chunk text', score: 0.9 },
    ]
    useAppStore.getState().setMessageSources('msg-1', sources)
    expect(useAppStore.getState().messages[0].sources).toEqual(sources)
  })
})

describe('setStreamingError', () => {
  it('replaces last assistant message content with error text', () => {
    useAppStore.getState().addMessage({ id: '1', role: 'assistant', content: '' })
    useAppStore.getState().setStreamingError('timeout')
    expect(useAppStore.getState().messages[0].content).toBe('Error: timeout')
    expect(useAppStore.getState().isStreaming).toBe(false)
  })
})

describe('clearChat', () => {
  it('clears messages and generates a new session id', () => {
    useAppStore.getState().addMessage({ id: '1', role: 'user', content: 'hi' })
    const oldSession = useAppStore.getState().sessionId
    useAppStore.getState().clearChat()
    expect(useAppStore.getState().messages).toHaveLength(0)
    expect(useAppStore.getState().sessionId).not.toBe(oldSession)
  })
})

describe('toggleTheme', () => {
  it('switches from dark to light', () => {
    expect(useAppStore.getState().theme).toBe('dark')
    useAppStore.getState().toggleTheme()
    expect(useAppStore.getState().theme).toBe('light')
  })

  it('switches from light to dark', () => {
    useAppStore.setState({ theme: 'light' })
    useAppStore.getState().toggleTheme()
    expect(useAppStore.getState().theme).toBe('dark')
  })
})

describe('setDocuments', () => {
  it('replaces the documents list', () => {
    const docs: DocumentStatus[] = [
      { doc_id: 'd1', filename: 'a.pdf', status: 'ready', created_at: '' },
    ]
    useAppStore.getState().setDocuments(docs)
    expect(useAppStore.getState().documents).toEqual(docs)
  })
})
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
cd frontend && npm test -- __tests__/store.test.ts
```

Expected: `Cannot find module '@/lib/store'` or similar import error.

- [ ] **Step 3: Create `frontend/lib/store.ts`**

```ts
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Message, DocumentStatus, SourceChunk } from '@/types'

interface AppState {
  messages: Message[]
  sessionId: string
  isStreaming: boolean
  documents: DocumentStatus[]
  selectedDocId: string | null
  isPolling: boolean
  theme: 'dark' | 'light'

  addMessage: (msg: Message) => void
  appendToken: (token: string) => void
  setMessageSources: (messageId: string, sources: SourceChunk[]) => void
  setStreaming: (streaming: boolean) => void
  setStreamingError: (error: string) => void
  clearChat: () => void
  setDocuments: (docs: DocumentStatus[]) => void
  setSelectedDocId: (id: string | null) => void
  setPolling: (polling: boolean) => void
  toggleTheme: () => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      messages: [],
      sessionId: crypto.randomUUID(),
      isStreaming: false,
      documents: [],
      selectedDocId: null,
      isPolling: false,
      theme: 'dark',

      addMessage: (msg) =>
        set((s) => ({ messages: [...s.messages, msg] })),

      appendToken: (token) =>
        set((s) => {
          const msgs = [...s.messages]
          const last = msgs[msgs.length - 1]
          if (last?.role === 'assistant') {
            msgs[msgs.length - 1] = { ...last, content: last.content + token }
          }
          return { messages: msgs }
        }),

      setMessageSources: (messageId, sources) =>
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === messageId ? { ...m, sources } : m
          ),
        })),

      setStreaming: (streaming) => set({ isStreaming: streaming }),

      setStreamingError: (error) =>
        set((s) => {
          const msgs = [...s.messages]
          const last = msgs[msgs.length - 1]
          if (last?.role === 'assistant') {
            msgs[msgs.length - 1] = { ...last, content: `Error: ${error}` }
          }
          return { messages: msgs, isStreaming: false }
        }),

      clearChat: () =>
        set({ messages: [], sessionId: crypto.randomUUID() }),

      setDocuments: (docs) => set({ documents: docs }),
      setSelectedDocId: (id) => set({ selectedDocId: id }),
      setPolling: (polling) => set({ isPolling: polling }),

      toggleTheme: () =>
        set((s) => ({ theme: s.theme === 'dark' ? 'light' : 'dark' })),
    }),
    {
      name: 'rag-store',
      partialize: (s) => ({ theme: s.theme }),
    }
  )
)
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
cd frontend && npm test -- __tests__/store.test.ts
```

Expected:
```
✓ __tests__/store.test.ts (9)
Test Files  1 passed (1)
Tests       9 passed (9)
```

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/lib/store.ts frontend/__tests__/store.test.ts
git commit -m "feat: add Zustand store with chat and document state"
```

---

### Task 6: API client — non-streaming endpoints (TDD)

**Files:**
- Create: `frontend/__tests__/api.test.ts`
- Create: `frontend/lib/api.ts` (non-streaming portion)

- [ ] **Step 1: Write the failing tests**

Create `frontend/__tests__/api.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fetchDocuments, uploadDocument, deleteDocument } from '@/lib/api'
import type { DocumentStatus } from '@/types'

const API = 'http://localhost:8000'

beforeEach(() => {
  vi.resetAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

const mockDoc: DocumentStatus = {
  doc_id: 'doc-1',
  filename: 'test.pdf',
  status: 'ready',
  created_at: '2026-01-01T00:00:00Z',
  chunk_count: 10,
}

describe('fetchDocuments', () => {
  it('returns parsed document list on success', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([mockDoc]),
    })
    const result = await fetchDocuments()
    expect(result).toEqual([mockDoc])
    expect(fetch).toHaveBeenCalledWith(`${API}/documents`)
  })

  it('returns empty array when fetch throws', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Network error'))
    const result = await fetchDocuments()
    expect(result).toEqual([])
  })

  it('returns empty array on non-ok response', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 500 })
    const result = await fetchDocuments()
    expect(result).toEqual([])
  })
})

describe('uploadDocument', () => {
  it('sends file as FormData and returns response', async () => {
    const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ doc_id: 'doc-1', filename: 'test.pdf', status: 'processing' }),
    })
    const result = await uploadDocument(file)
    expect(result).toEqual({ doc_id: 'doc-1', filename: 'test.pdf', status: 'processing' })
    const call = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(call[0]).toBe(`${API}/upload`)
    expect(call[1].method).toBe('POST')
    expect(call[1].body).toBeInstanceOf(FormData)
  })

  it('throws on upload failure', async () => {
    const file = new File(['x'], 'bad.exe')
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 415,
      text: () => Promise.resolve('Unsupported'),
    })
    await expect(uploadDocument(file)).rejects.toThrow('Upload failed: 415')
  })
})

describe('deleteDocument', () => {
  it('sends DELETE request to correct URL', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true })
    await deleteDocument('doc-1')
    expect(fetch).toHaveBeenCalledWith(`${API}/documents/doc-1`, { method: 'DELETE' })
  })

  it('does not throw on failure (silent delete)', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404 })
    await expect(deleteDocument('missing')).resolves.toBeUndefined()
  })
})
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
cd frontend && npm test -- __tests__/api.test.ts
```

Expected: `Cannot find module '@/lib/api'`.

- [ ] **Step 3: Create `frontend/lib/api.ts` with non-streaming functions**

```ts
import type { DocumentStatus, SourceChunk, UploadResponse } from '@/types'

const API_URL =
  (typeof process !== 'undefined' && process.env.NEXT_PUBLIC_API_URL) ||
  'http://localhost:8000'

export async function fetchDocuments(): Promise<DocumentStatus[]> {
  try {
    const res = await fetch(`${API_URL}/documents`)
    if (!res.ok) return []
    return res.json()
  } catch {
    return []
  }
}

export async function uploadDocument(file: File): Promise<UploadResponse> {
  const body = new FormData()
  body.append('file', file)
  const res = await fetch(`${API_URL}/upload`, { method: 'POST', body })
  if (!res.ok) {
    throw new Error(`Upload failed: ${res.status}`)
  }
  return res.json()
}

export async function deleteDocument(docId: string): Promise<void> {
  try {
    await fetch(`${API_URL}/documents/${docId}`, { method: 'DELETE' })
  } catch {
    // silent — best-effort delete
  }
}

export interface StreamPayload {
  question: string
  session_id: string
  doc_id?: string
}

export async function streamAnswer(
  payload: StreamPayload,
  onToken: (token: string) => void,
  onSources: (sources: SourceChunk[]) => void,
  onDone: () => void,
  onError: (error: string) => void
): Promise<void> {
  // Implemented in Task 7
  void payload; void onToken; void onSources; void onDone; void onError
}
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
cd frontend && npm test -- __tests__/api.test.ts
```

Expected:
```
✓ __tests__/api.test.ts (7)
Test Files  1 passed (1)
Tests       7 passed (7)
```

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/lib/api.ts frontend/__tests__/api.test.ts
git commit -m "feat: add API client for fetchDocuments, uploadDocument, deleteDocument"
```

---

### Task 7: API client — streamAnswer (TDD)

**Files:**
- Modify: `frontend/__tests__/api.test.ts` (add streaming tests)
- Modify: `frontend/lib/api.ts` (implement `streamAnswer`)

- [ ] **Step 1: Add streaming tests to `frontend/__tests__/api.test.ts`**

Append the following to the existing test file:

```ts
import { streamAnswer } from '@/lib/api'

function makeSSEStream(events: unknown[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const event of events) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`))
      }
      controller.close()
    },
  })
}

describe('streamAnswer', () => {
  it('calls onToken for each token event', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: makeSSEStream([
        { type: 'token', data: 'Hello' },
        { type: 'token', data: ' world' },
        { type: 'done', data: null },
      ]),
    })

    const tokens: string[] = []
    const onDone = vi.fn()
    await streamAnswer(
      { question: 'q', session_id: 'sid' },
      (t) => tokens.push(t),
      vi.fn(),
      onDone,
      vi.fn()
    )
    expect(tokens).toEqual(['Hello', ' world'])
    expect(onDone).toHaveBeenCalledOnce()
  })

  it('calls onSources with source chunks', async () => {
    const sources = [{ doc_id: 'd1', filename: 'a.pdf', text: 'chunk', score: 0.9 }]
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: makeSSEStream([
        { type: 'sources', data: sources },
        { type: 'done', data: null },
      ]),
    })

    const onSources = vi.fn()
    await streamAnswer({ question: 'q', session_id: 'sid' }, vi.fn(), onSources, vi.fn(), vi.fn())
    expect(onSources).toHaveBeenCalledWith(sources)
  })

  it('calls onError on SSE error event', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: makeSSEStream([{ type: 'error', data: 'LLM timeout' }]),
    })

    const onError = vi.fn()
    await streamAnswer({ question: 'q', session_id: 'sid' }, vi.fn(), vi.fn(), vi.fn(), onError)
    expect(onError).toHaveBeenCalledWith('LLM timeout')
  })

  it('calls onError when fetch fails', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('connection refused'))
    const onError = vi.fn()
    await streamAnswer({ question: 'q', session_id: 'sid' }, vi.fn(), vi.fn(), vi.fn(), onError)
    expect(onError).toHaveBeenCalledWith(expect.stringContaining('reach API'))
  })

  it('calls onError on non-ok HTTP response', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 409 })
    const onError = vi.fn()
    await streamAnswer({ question: 'q', session_id: 'sid' }, vi.fn(), vi.fn(), vi.fn(), onError)
    expect(onError).toHaveBeenCalledWith('API error 409')
  })
})
```

- [ ] **Step 2: Run new tests — confirm they fail**

```bash
cd frontend && npm test -- __tests__/api.test.ts
```

Expected: streaming tests fail because `streamAnswer` is a no-op stub.

- [ ] **Step 3: Implement `streamAnswer` in `frontend/lib/api.ts`**

Replace the stub `streamAnswer` function with the full implementation:

```ts
export async function streamAnswer(
  payload: StreamPayload,
  onToken: (token: string) => void,
  onSources: (sources: SourceChunk[]) => void,
  onDone: () => void,
  onError: (error: string) => void
): Promise<void> {
  let response: Response
  try {
    response = await fetch(`${API_URL}/ask/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  } catch {
    onError('Cannot reach API. Is the server running?')
    return
  }

  if (!response.ok) {
    onError(`API error ${response.status}`)
    return
  }

  if (!response.body) {
    onError('No response body from server')
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''

    for (const part of parts) {
      const line = part.trim()
      if (!line.startsWith('data: ')) continue
      try {
        const event = JSON.parse(line.slice(6)) as { type: string; data: unknown }
        if (event.type === 'token') onToken(event.data as string)
        else if (event.type === 'sources') onSources(event.data as SourceChunk[])
        else if (event.type === 'done') onDone()
        else if (event.type === 'error') onError(event.data as string)
      } catch {
        // malformed SSE line — skip
      }
    }
  }
}
```

- [ ] **Step 4: Run all API tests — confirm they pass**

```bash
cd frontend && npm test -- __tests__/api.test.ts
```

Expected:
```
✓ __tests__/api.test.ts (12)
Test Files  1 passed (1)
Tests       12 passed (12)
```

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/lib/api.ts frontend/__tests__/api.test.ts
git commit -m "feat: implement streamAnswer with SSE ReadableStream parsing"
```

---

### Task 8: ThemeProvider + ThemeToggle (TDD)

**Files:**
- Create: `frontend/__tests__/components.test.tsx`
- Create: `frontend/components/ThemeProvider.tsx`
- Create: `frontend/components/ThemeToggle.tsx`

- [ ] **Step 1: Write the failing tests**

Create `frontend/__tests__/components.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { useAppStore } from '@/lib/store'

beforeEach(() => {
  useAppStore.setState({
    messages: [],
    sessionId: 'test-session',
    isStreaming: false,
    documents: [],
    selectedDocId: null,
    isPolling: false,
    theme: 'dark',
  })
  document.documentElement.className = ''
})

describe('ThemeProvider', () => {
  it('adds dark class to html element when theme is dark', async () => {
    const { ThemeProvider } = await import('@/components/ThemeProvider')
    render(<ThemeProvider><div /></ThemeProvider>)
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('removes dark class when theme is light', async () => {
    useAppStore.setState({ theme: 'light' })
    const { ThemeProvider } = await import('@/components/ThemeProvider')
    render(<ThemeProvider><div /></ThemeProvider>)
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })
})

describe('ThemeToggle', () => {
  it('renders a button', async () => {
    const { ThemeToggle } = await import('@/components/ThemeToggle')
    render(<ThemeToggle />)
    expect(screen.getByRole('button')).toBeInTheDocument()
  })

  it('calls toggleTheme when clicked', async () => {
    const { ThemeToggle } = await import('@/components/ThemeToggle')
    render(<ThemeToggle />)
    fireEvent.click(screen.getByRole('button'))
    expect(useAppStore.getState().theme).toBe('light')
  })
})
```

- [ ] **Step 2: Run — confirm they fail**

```bash
cd frontend && npm test -- __tests__/components.test.tsx
```

Expected: `Cannot find module '@/components/ThemeProvider'`.

- [ ] **Step 3: Create `frontend/components/ThemeProvider.tsx`**

```tsx
'use client'

import { useEffect } from 'react'
import { useAppStore } from '@/lib/store'

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const theme = useAppStore((s) => s.theme)

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'dark') {
      root.classList.add('dark')
    } else {
      root.classList.remove('dark')
    }
  }, [theme])

  return <>{children}</>
}
```

- [ ] **Step 4: Create `frontend/components/ThemeToggle.tsx`**

```tsx
'use client'

import { useAppStore } from '@/lib/store'

export function ThemeToggle() {
  const theme = useAppStore((s) => s.theme)
  const toggleTheme = useAppStore((s) => s.toggleTheme)

  return (
    <button
      onClick={toggleTheme}
      aria-label="Toggle theme"
      className="p-2 rounded-lg text-sm hover:bg-slate-700 dark:hover:bg-slate-700 hover:bg-gray-200 transition-colors"
    >
      {theme === 'dark' ? '☀️ Light' : '🌙 Dark'}
    </button>
  )
}
```

- [ ] **Step 5: Run — confirm tests pass**

```bash
cd frontend && npm test -- __tests__/components.test.tsx
```

Expected:
```
✓ __tests__/components.test.tsx > ThemeProvider > adds dark class ...
✓ __tests__/components.test.tsx > ThemeProvider > removes dark class ...
✓ __tests__/components.test.tsx > ThemeToggle > renders a button
✓ __tests__/components.test.tsx > ThemeToggle > calls toggleTheme when clicked
```

- [ ] **Step 6: Commit**

```bash
cd ..
git add frontend/components/ThemeProvider.tsx frontend/components/ThemeToggle.tsx frontend/__tests__/components.test.tsx
git commit -m "feat: add ThemeProvider and ThemeToggle components"
```

---

### Task 9: DocumentCard (TDD)

**Files:**
- Modify: `frontend/__tests__/components.test.tsx` (add DocumentCard tests)
- Create: `frontend/components/DocumentCard.tsx`

- [ ] **Step 1: Append DocumentCard tests to `frontend/__tests__/components.test.tsx`**

```tsx
describe('DocumentCard', () => {
  const onDelete = vi.fn()

  it('renders filename', async () => {
    const { DocumentCard } = await import('@/components/DocumentCard')
    render(
      <DocumentCard
        doc={{ doc_id: 'd1', filename: 'report.pdf', status: 'ready', created_at: '', chunk_count: 5 }}
        onDelete={onDelete}
      />
    )
    expect(screen.getByText(/report\.pdf/)).toBeInTheDocument()
  })

  it('shows chunk count when ready', async () => {
    const { DocumentCard } = await import('@/components/DocumentCard')
    render(
      <DocumentCard
        doc={{ doc_id: 'd1', filename: 'doc.pdf', status: 'ready', created_at: '', chunk_count: 12 }}
        onDelete={onDelete}
      />
    )
    expect(screen.getByText(/12 chunks/)).toBeInTheDocument()
  })

  it('calls onDelete when delete button clicked', async () => {
    const { DocumentCard } = await import('@/components/DocumentCard')
    render(
      <DocumentCard
        doc={{ doc_id: 'd1', filename: 'doc.pdf', status: 'ready', created_at: '' }}
        onDelete={onDelete}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /delete/i }))
    expect(onDelete).toHaveBeenCalledWith('d1')
  })

  it('shows processing indicator for processing status', async () => {
    const { DocumentCard } = await import('@/components/DocumentCard')
    render(
      <DocumentCard
        doc={{ doc_id: 'd1', filename: 'doc.pdf', status: 'processing', created_at: '' }}
        onDelete={onDelete}
      />
    )
    expect(screen.getByText(/processing/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run — confirm new tests fail**

```bash
cd frontend && npm test -- __tests__/components.test.tsx
```

Expected: `Cannot find module '@/components/DocumentCard'`.

- [ ] **Step 3: Create `frontend/components/DocumentCard.tsx`**

```tsx
'use client'

import type { DocumentStatus } from '@/types'

const STATUS_BADGE: Record<DocumentStatus['status'], string> = {
  ready: '🟢',
  processing: '🟡',
  failed: '🔴',
}

interface Props {
  doc: DocumentStatus
  onDelete: (docId: string) => void
}

export function DocumentCard({ doc, onDelete }: Props) {
  return (
    <div className="flex items-center justify-between gap-2 py-1.5 px-2 rounded hover:bg-slate-800 dark:hover:bg-slate-800 hover:bg-gray-100 group">
      <div className="flex items-center gap-2 min-w-0">
        <span title={doc.status}>{STATUS_BADGE[doc.status]}</span>
        <span className="text-sm truncate">{doc.filename}</span>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {doc.status === 'ready' && doc.chunk_count != null && (
          <span className="text-xs text-slate-400 dark:text-slate-400 text-gray-500">
            {doc.chunk_count} chunks
          </span>
        )}
        {doc.status === 'processing' && (
          <span className="text-xs text-yellow-400 dark:text-yellow-400 text-yellow-600">
            processing
          </span>
        )}
        {doc.status === 'failed' && (
          <span className="text-xs text-red-400 dark:text-red-400 text-red-600" title={doc.error}>
            failed
          </span>
        )}
        <button
          aria-label="Delete document"
          onClick={() => onDelete(doc.doc_id)}
          className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-400 transition-all text-xs px-1"
        >
          ✕
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run — confirm all tests pass**

```bash
cd frontend && npm test -- __tests__/components.test.tsx
```

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/components/DocumentCard.tsx frontend/__tests__/components.test.tsx
git commit -m "feat: add DocumentCard component with status badge and delete"
```

---

### Task 10: SourcesExpander (TDD)

**Files:**
- Modify: `frontend/__tests__/components.test.tsx`
- Create: `frontend/components/SourcesExpander.tsx`

- [ ] **Step 1: Append SourcesExpander tests**

```tsx
describe('SourcesExpander', () => {
  const sources: import('@/types').SourceChunk[] = [
    { doc_id: 'd1', filename: 'report.pdf', page_number: 3, text: 'some text here', score: 0.92 },
    { doc_id: 'd2', filename: 'notes.txt', text: 'other text', score: 0.85 },
  ]

  it('renders a toggle button with source count', async () => {
    const { SourcesExpander } = await import('@/components/SourcesExpander')
    render(<SourcesExpander sources={sources} />)
    expect(screen.getByText(/2 sources/i)).toBeInTheDocument()
  })

  it('hides source details by default', async () => {
    const { SourcesExpander } = await import('@/components/SourcesExpander')
    render(<SourcesExpander sources={sources} />)
    expect(screen.queryByText('some text here')).not.toBeInTheDocument()
  })

  it('shows source details after clicking toggle', async () => {
    const { SourcesExpander } = await import('@/components/SourcesExpander')
    render(<SourcesExpander sources={sources} />)
    fireEvent.click(screen.getByText(/2 sources/i))
    expect(screen.getByText('some text here')).toBeInTheDocument()
    expect(screen.getByText(/report\.pdf/)).toBeInTheDocument()
  })

  it('shows singular label for one source', async () => {
    const { SourcesExpander } = await import('@/components/SourcesExpander')
    render(<SourcesExpander sources={[sources[0]]} />)
    expect(screen.getByText(/1 source/i)).toBeInTheDocument()
    expect(screen.queryByText(/1 sources/i)).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run — confirm new tests fail**

```bash
cd frontend && npm test -- __tests__/components.test.tsx
```

- [ ] **Step 3: Create `frontend/components/SourcesExpander.tsx`**

```tsx
'use client'

import { useState } from 'react'
import type { SourceChunk } from '@/types'

interface Props {
  sources: SourceChunk[]
}

export function SourcesExpander({ sources }: Props) {
  const [open, setOpen] = useState(false)
  const label = `${sources.length} source${sources.length !== 1 ? 's' : ''}`

  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className="text-xs text-blue-400 dark:text-blue-400 text-blue-600 hover:underline flex items-center gap-1"
      >
        <span>{open ? '▾' : '▸'}</span>
        <span>{label}</span>
      </button>

      {open && (
        <div className="mt-2 space-y-2">
          {sources.map((src, i) => (
            <div
              key={i}
              className="p-3 rounded-lg bg-slate-800 dark:bg-slate-800 bg-gray-100 text-sm"
            >
              <div className="flex items-center gap-2 mb-1">
                <span className="font-medium">{src.filename}</span>
                {src.page_number != null && (
                  <span className="text-slate-400 dark:text-slate-400 text-gray-500">
                    p.{src.page_number}
                  </span>
                )}
                <span className="ml-auto text-slate-500 text-xs">
                  score {src.score.toFixed(3)}
                </span>
              </div>
              <p className="text-slate-300 dark:text-slate-300 text-gray-700 line-clamp-3 text-xs leading-relaxed">
                {src.text}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run — confirm all tests pass**

```bash
cd frontend && npm test -- __tests__/components.test.tsx
```

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/components/SourcesExpander.tsx frontend/__tests__/components.test.tsx
git commit -m "feat: add SourcesExpander collapsible citations component"
```

---

### Task 11: Sidebar (TDD)

**Files:**
- Modify: `frontend/__tests__/components.test.tsx`
- Create: `frontend/components/Sidebar.tsx`

- [ ] **Step 1: Append Sidebar tests**

```tsx
describe('Sidebar', () => {
  beforeEach(() => {
    vi.mock('@/lib/api', () => ({
      fetchDocuments: vi.fn().mockResolvedValue([]),
      uploadDocument: vi.fn(),
      deleteDocument: vi.fn(),
      streamAnswer: vi.fn(),
    }))
    useAppStore.setState({
      messages: [],
      sessionId: 'sid',
      isStreaming: false,
      documents: [
        { doc_id: 'd1', filename: 'report.pdf', status: 'ready', created_at: '', chunk_count: 5 },
      ],
      selectedDocId: null,
      isPolling: false,
      theme: 'dark',
    })
  })

  it('renders the document list from the store', async () => {
    const { Sidebar } = await import('@/components/Sidebar')
    render(<Sidebar />)
    expect(screen.getByText(/report\.pdf/)).toBeInTheDocument()
  })

  it('renders the scope selector with all-docs option', async () => {
    const { Sidebar } = await import('@/components/Sidebar')
    render(<Sidebar />)
    expect(screen.getByText(/All documents/i)).toBeInTheDocument()
  })

  it('renders a clear chat button', async () => {
    const { Sidebar } = await import('@/components/Sidebar')
    render(<Sidebar />)
    expect(screen.getByText(/clear chat/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run — confirm new tests fail**

```bash
cd frontend && npm test -- __tests__/components.test.tsx
```

- [ ] **Step 3: Create `frontend/components/Sidebar.tsx`**

```tsx
'use client'

import { useCallback, useEffect, useRef } from 'react'
import { useAppStore } from '@/lib/store'
import { fetchDocuments, uploadDocument, deleteDocument } from '@/lib/api'
import { DocumentCard } from './DocumentCard'
import { ThemeToggle } from './ThemeToggle'

export function Sidebar() {
  const documents = useAppStore((s) => s.documents)
  const selectedDocId = useAppStore((s) => s.selectedDocId)
  const isPolling = useAppStore((s) => s.isPolling)
  const setDocuments = useAppStore((s) => s.setDocuments)
  const setSelectedDocId = useAppStore((s) => s.setSelectedDocId)
  const setPolling = useAppStore((s) => s.setPolling)
  const clearChat = useAppStore((s) => s.clearChat)

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const refreshDocs = useCallback(async () => {
    const docs = await fetchDocuments()
    setDocuments(docs)
    if (!docs.some((d) => d.status === 'processing')) {
      if (pollingRef.current) clearInterval(pollingRef.current)
      pollingRef.current = null
      setPolling(false)
    }
  }, [setDocuments, setPolling])

  const startPolling = useCallback(() => {
    if (pollingRef.current) return
    setPolling(true)
    pollingRef.current = setInterval(refreshDocs, 2000)
  }, [refreshDocs, setPolling])

  useEffect(() => {
    refreshDocs()
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current)
    }
  }, [refreshDocs])

  async function handleUpload(files: FileList | null) {
    if (!files) return
    for (const file of Array.from(files)) {
      try {
        await uploadDocument(file)
      } catch (err) {
        console.error('Upload failed:', err)
      }
    }
    await refreshDocs()
    startPolling()
  }

  async function handleDelete(docId: string) {
    await deleteDocument(docId)
    if (selectedDocId === docId) setSelectedDocId(null)
    await refreshDocs()
  }

  const readyDocs = documents.filter((d) => d.status === 'ready')

  return (
    <aside className="w-64 shrink-0 flex flex-col h-full border-r border-slate-700 dark:border-slate-700 border-gray-200 bg-slate-900 dark:bg-slate-900 bg-white">
      <div className="p-4 border-b border-slate-700 dark:border-slate-700 border-gray-200">
        <h1 className="font-semibold text-sm tracking-wide uppercase text-slate-400 dark:text-slate-400 text-gray-500">
          Documents
        </h1>
      </div>

      {/* Upload zone */}
      <div className="p-3">
        <label className="block cursor-pointer border-2 border-dashed border-slate-600 dark:border-slate-600 border-gray-300 rounded-lg p-4 text-center text-sm text-slate-400 dark:text-slate-400 text-gray-500 hover:border-blue-500 hover:text-blue-400 transition-colors">
          <input
            type="file"
            accept=".pdf,.txt,.docx,.md"
            multiple
            className="sr-only"
            onChange={(e) => handleUpload(e.target.files)}
          />
          {isPolling ? '⏳ Processing…' : '+ Upload document'}
        </label>
      </div>

      {/* Document list */}
      <div className="flex-1 overflow-y-auto px-2 py-1">
        {documents.length === 0 ? (
          <p className="text-xs text-slate-500 text-center mt-4">No documents yet.</p>
        ) : (
          documents.map((doc) => (
            <DocumentCard key={doc.doc_id} doc={doc} onDelete={handleDelete} />
          ))
        )}
      </div>

      {/* Scope selector */}
      <div className="p-3 border-t border-slate-700 dark:border-slate-700 border-gray-200">
        <label className="block text-xs text-slate-400 dark:text-slate-400 text-gray-500 mb-1">
          Query scope
        </label>
        <select
          value={selectedDocId ?? ''}
          onChange={(e) => setSelectedDocId(e.target.value || null)}
          className="w-full text-sm rounded-lg px-2 py-1.5 bg-slate-800 dark:bg-slate-800 bg-gray-100 border border-slate-600 dark:border-slate-600 border-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-500"
        >
          <option value="">All documents</option>
          {readyDocs.map((d) => (
            <option key={d.doc_id} value={d.doc_id}>
              {d.filename}
            </option>
          ))}
        </select>
      </div>

      {/* Footer actions */}
      <div className="p-3 border-t border-slate-700 dark:border-slate-700 border-gray-200 flex items-center justify-between">
        <button
          onClick={clearChat}
          className="text-xs text-slate-400 hover:text-slate-200 dark:hover:text-slate-200 hover:text-gray-700 transition-colors"
        >
          Clear chat
        </button>
        <ThemeToggle />
      </div>
    </aside>
  )
}
```

- [ ] **Step 4: Run — confirm tests pass**

```bash
cd frontend && npm test -- __tests__/components.test.tsx
```

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/components/Sidebar.tsx frontend/__tests__/components.test.tsx
git commit -m "feat: add Sidebar with upload, document list, scope selector"
```

---

### Task 12: ChatInput (TDD)

**Files:**
- Modify: `frontend/__tests__/components.test.tsx`
- Create: `frontend/components/ChatInput.tsx`

- [ ] **Step 1: Append ChatInput tests**

```tsx
describe('ChatInput', () => {
  it('renders a text input and send button', async () => {
    const { ChatInput } = await import('@/components/ChatInput')
    render(<ChatInput onSend={vi.fn()} />)
    expect(screen.getByPlaceholderText(/ask a question/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /send/i })).toBeInTheDocument()
  })

  it('calls onSend with trimmed input on button click', async () => {
    const { ChatInput } = await import('@/components/ChatInput')
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)
    const input = screen.getByPlaceholderText(/ask a question/i)
    fireEvent.change(input, { target: { value: '  hello  ' } })
    fireEvent.click(screen.getByRole('button', { name: /send/i }))
    expect(onSend).toHaveBeenCalledWith('hello')
  })

  it('clears input after sending', async () => {
    const { ChatInput } = await import('@/components/ChatInput')
    render(<ChatInput onSend={vi.fn()} />)
    const input = screen.getByPlaceholderText(/ask a question/i) as HTMLInputElement
    fireEvent.change(input, { target: { value: 'hello' } })
    fireEvent.click(screen.getByRole('button', { name: /send/i }))
    expect(input.value).toBe('')
  })

  it('does not call onSend for empty input', async () => {
    const { ChatInput } = await import('@/components/ChatInput')
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)
    fireEvent.click(screen.getByRole('button', { name: /send/i }))
    expect(onSend).not.toHaveBeenCalled()
  })

  it('disables the button when disabled prop is true', async () => {
    const { ChatInput } = await import('@/components/ChatInput')
    render(<ChatInput onSend={vi.fn()} disabled />)
    expect(screen.getByRole('button', { name: /send/i })).toBeDisabled()
  })
})
```

- [ ] **Step 2: Run — confirm new tests fail**

```bash
cd frontend && npm test -- __tests__/components.test.tsx
```

- [ ] **Step 3: Create `frontend/components/ChatInput.tsx`**

```tsx
'use client'

import { useState, type KeyboardEvent } from 'react'

interface Props {
  onSend: (question: string) => void
  disabled?: boolean
}

export function ChatInput({ onSend, disabled = false }: Props) {
  const [value, setValue] = useState('')

  function handleSend() {
    const trimmed = value.trim()
    if (!trimmed) return
    onSend(trimmed)
    setValue('')
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="p-4 border-t border-slate-700 dark:border-slate-700 border-gray-200 bg-slate-900 dark:bg-slate-900 bg-white">
      <div className="flex gap-2">
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question about your documents…"
          disabled={disabled}
          className="flex-1 rounded-lg px-4 py-2.5 text-sm bg-slate-800 dark:bg-slate-800 bg-gray-100 border border-slate-600 dark:border-slate-600 border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
        />
        <button
          onClick={handleSend}
          disabled={disabled}
          aria-label="Send"
          className="px-4 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          →
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run — confirm tests pass**

```bash
cd frontend && npm test -- __tests__/components.test.tsx
```

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/components/ChatInput.tsx frontend/__tests__/components.test.tsx
git commit -m "feat: add ChatInput with send on Enter and disabled state"
```

---

### Task 13: ChatWindow (TDD)

**Files:**
- Modify: `frontend/__tests__/components.test.tsx`
- Create: `frontend/components/ChatWindow.tsx`

- [ ] **Step 1: Append ChatWindow tests**

```tsx
describe('ChatWindow', () => {
  it('renders empty state when no messages', async () => {
    const { ChatWindow } = await import('@/components/ChatWindow')
    render(<ChatWindow />)
    expect(screen.getByText(/upload a document/i)).toBeInTheDocument()
  })

  it('renders user and assistant messages', async () => {
    useAppStore.setState({
      ...useAppStore.getState(),
      messages: [
        { id: '1', role: 'user', content: 'What is RAG?' },
        { id: '2', role: 'assistant', content: 'RAG stands for Retrieval-Augmented Generation.' },
      ],
    })
    const { ChatWindow } = await import('@/components/ChatWindow')
    render(<ChatWindow />)
    expect(screen.getByText('What is RAG?')).toBeInTheDocument()
    expect(screen.getByText(/Retrieval-Augmented Generation/)).toBeInTheDocument()
  })

  it('shows streaming cursor when isStreaming is true', async () => {
    useAppStore.setState({
      ...useAppStore.getState(),
      isStreaming: true,
      messages: [{ id: '1', role: 'assistant', content: 'Partial answer' }],
    })
    const { ChatWindow } = await import('@/components/ChatWindow')
    render(<ChatWindow />)
    expect(screen.getByText(/▌/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run — confirm new tests fail**

```bash
cd frontend && npm test -- __tests__/components.test.tsx
```

- [ ] **Step 3: Create `frontend/components/ChatWindow.tsx`**

`ChatWindow` is a pure rendering component. It reads from the Zustand store and displays messages. Streaming logic lives in `useChat` (Task 14).

```tsx
'use client'

import { useEffect, useRef } from 'react'
import { useAppStore } from '@/lib/store'
import { SourcesExpander } from './SourcesExpander'

export function ChatWindow() {
  const messages = useAppStore((s) => s.messages)
  const isStreaming = useAppStore((s) => s.isStreaming)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-slate-500 dark:text-slate-500 text-gray-400 text-sm">
        Upload a document and ask a question to get started.
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
      {messages.map((msg, i) => {
        const isLast = i === messages.length - 1
        const showCursor = isLast && msg.role === 'assistant' && isStreaming

        return (
          <div
            key={msg.id}
            className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
          >
            <div
              className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700 dark:bg-slate-700 bg-gray-200'
              }`}
            >
              {msg.role === 'user' ? 'U' : 'AI'}
            </div>
            <div className="max-w-prose">
              <p className="text-sm leading-relaxed whitespace-pre-wrap">
                {msg.content}
                {showCursor && <span className="animate-pulse">▌</span>}
              </p>
              {msg.sources && msg.sources.length > 0 && (
                <SourcesExpander sources={msg.sources} />
              )}
            </div>
          </div>
        )
      })}
      <div ref={bottomRef} />
    </div>
  )
}
```

- [ ] **Step 4: Run — confirm tests pass**

```bash
cd frontend && npm test -- __tests__/components.test.tsx
```

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/components/ChatWindow.tsx frontend/__tests__/components.test.tsx
git commit -m "feat: add ChatWindow pure renderer with streaming cursor and sources"
```

---

### Task 14: Wire app/layout.tsx and app/page.tsx

**Files:**
- Modify: `frontend/app/layout.tsx`
- Modify: `frontend/app/page.tsx`
- Create: `frontend/lib/useChat.ts`
- Create: `frontend/.env.local`
- Modify: `frontend/next.config.ts`

- [ ] **Step 1: Create `frontend/.env.local`**

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

- [ ] **Step 2: Replace `frontend/next.config.ts`**

```ts
import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  output: 'standalone',
}

export default nextConfig
```

- [ ] **Step 3: Replace `frontend/app/layout.tsx`**

```tsx
import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { ThemeProvider } from '@/components/ThemeProvider'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'RAG Document Intelligence',
  description: 'Ask questions about your documents',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  )
}
```

- [ ] **Step 4: Create `frontend/lib/useChat.ts`**

This hook owns the streaming logic — adds messages to the store and calls `streamAnswer`. `page.tsx` calls `sendMessage` from here.

```ts
'use client'

import { useAppStore } from './store'
import { streamAnswer } from './api'
import type { SourceChunk } from '@/types'

export function useChat() {
  const addMessage = useAppStore((s) => s.addMessage)
  const appendToken = useAppStore((s) => s.appendToken)
  const setMessageSources = useAppStore((s) => s.setMessageSources)
  const setStreaming = useAppStore((s) => s.setStreaming)
  const setStreamingError = useAppStore((s) => s.setStreamingError)
  const isStreaming = useAppStore((s) => s.isStreaming)
  const sessionId = useAppStore((s) => s.sessionId)
  const selectedDocId = useAppStore((s) => s.selectedDocId)

  async function sendMessage(question: string) {
    if (isStreaming) return
    addMessage({ id: crypto.randomUUID(), role: 'user', content: question })
    const assistantId = crypto.randomUUID()
    addMessage({ id: assistantId, role: 'assistant', content: '' })
    setStreaming(true)
    await streamAnswer(
      { question, session_id: sessionId, doc_id: selectedDocId ?? undefined },
      (token: string) => appendToken(token),
      (sources: SourceChunk[]) => setMessageSources(assistantId, sources),
      () => setStreaming(false),
      (error: string) => setStreamingError(error)
    )
  }

  return { sendMessage, isStreaming }
}
```

Replace `frontend/app/page.tsx`:

```tsx
'use client'

import { Sidebar } from '@/components/Sidebar'
import { ChatWindow } from '@/components/ChatWindow'
import { ChatInput } from '@/components/ChatInput'
import { useChat } from '@/lib/useChat'

export default function Page() {
  const { sendMessage, isStreaming } = useChat()

  return (
    <main className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0">
        <header className="px-6 py-3 border-b border-slate-700 dark:border-slate-700 border-gray-200 shrink-0">
          <h2 className="text-sm font-medium text-slate-300 dark:text-slate-300 text-gray-700">
            🔍 RAG Document Intelligence
          </h2>
        </header>
        <ChatWindow />
        <ChatInput onSend={sendMessage} disabled={isStreaming} />
      </div>
    </main>
  )
}
```

- [ ] **Step 5: Verify TypeScript compiles with no errors**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 6: Run all tests**

```bash
npm test
```

Expected: all tests pass.

- [ ] **Step 7: Start the dev server and verify the app loads**

Ensure the FastAPI backend is running (`venv\Scripts\uvicorn main:app --reload` from the repo root), then:

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Verify:
- Dark background loads immediately
- Sidebar shows "No documents yet." with upload zone
- Theme toggle switches dark/light
- Chat area shows the empty state message

- [ ] **Step 8: Commit**

```bash
cd ..
git add frontend/app/layout.tsx frontend/app/page.tsx frontend/lib/useChat.ts frontend/components/ChatWindow.tsx frontend/.env.local frontend/next.config.ts
git commit -m "feat: wire app layout, page, and useChat hook"
```

---

### Task 15: frontend/Dockerfile

**Files:**
- Create: `frontend/Dockerfile`

- [ ] **Step 1: Create `frontend/Dockerfile`**

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --frozen-lockfile

COPY . .

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

# ── Runner ────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
```

- [ ] **Step 2: Add `.env.local` to `frontend/.gitignore`**

Open `frontend/.gitignore` (generated by `create-next-app`) and verify `.env.local` is listed. It should already be there. If not, add:

```
.env.local
```

- [ ] **Step 3: Commit**

```bash
git add frontend/Dockerfile frontend/.gitignore
git commit -m "feat: add frontend Dockerfile with two-stage standalone build"
```

---

### Task 16: Update docker-compose.yml and .env.example

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`

- [ ] **Step 1: Replace the `frontend` service in `docker-compose.yml`**

Open `docker-compose.yml`. Replace the entire `frontend:` service block (lines 26–42) with:

```yaml
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      args:
        NEXT_PUBLIC_API_URL: http://localhost:8000
    image: rag-frontend:latest
    container_name: rag-frontend
    depends_on:
      api:
        condition: service_healthy
    ports:
      - "3000:3000"
    restart: unless-stopped
```

Also update the `api` service's `CORS_ORIGINS` env var:

```yaml
      CORS_ORIGINS: ${CORS_ORIGINS:-http://localhost:3000}
```

The full updated `docker-compose.yml`:

```yaml
services:
  api:
    build: .
    image: rag-doc-intel:latest
    container_name: rag-api
    ports:
      - "8000:8000"
    environment:
      GROQ_API_KEY: ${GROQ_API_KEY}
      GROQ_CHAT_MODEL: ${GROQ_CHAT_MODEL:-llama-3.3-70b-versatile}
      EMBEDDING_MODEL: ${EMBEDDING_MODEL:-BAAI/bge-small-en-v1.5}
      EMBEDDING_DEVICE: ${EMBEDDING_DEVICE:-cpu}
      CHROMA_PERSIST_DIR: /app/data/chroma
      UPLOAD_DIR: /app/data/uploads
      CORS_ORIGINS: ${CORS_ORIGINS:-http://localhost:3000}
    volumes:
      - rag-data:/app/data
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8000/health"]
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 20s
    restart: unless-stopped

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      args:
        NEXT_PUBLIC_API_URL: http://localhost:8000
    image: rag-frontend:latest
    container_name: rag-frontend
    depends_on:
      api:
        condition: service_healthy
    ports:
      - "3000:3000"
    restart: unless-stopped

volumes:
  rag-data:
```

- [ ] **Step 2: Update `.env.example`**

Open `.env.example`. Find the `CORS_ORIGINS` line and change it to:

```
CORS_ORIGINS=http://localhost:3000
```

If there is no `CORS_ORIGINS` line, add it.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "feat: update Docker Compose to build and run Next.js frontend"
```

---

### Task 17: Delete app.py and final cleanup commit

**Files:**
- Delete: `app.py`

- [ ] **Step 1: Delete app.py**

```bash
git rm app.py
```

- [ ] **Step 2: Run all frontend tests one final time**

```bash
cd frontend && npm test
```

Expected: all tests pass.

- [ ] **Step 3: Verify TypeScript has no errors**

```bash
npx tsc --noEmit
cd ..
```

- [ ] **Step 4: Commit the deletion**

```bash
git commit -m "chore: remove Streamlit app.py, replaced by Next.js frontend"
```

- [ ] **Step 5: Push to GitHub**

```bash
git push origin main
```

---

## End-to-End Verification

After all tasks are complete, run the full stack:

```bash
# Terminal 1 — FastAPI backend
venv\Scripts\uvicorn main:app --reload

# Terminal 2 — Next.js frontend
cd frontend && npm run dev
```

Open [http://localhost:3000](http://localhost:3000) and verify:

1. Dark mode loads by default, theme toggle works
2. Upload a PDF — document card appears with 🟡, then transitions to 🟢 automatically
3. Select a document in the scope selector
4. Ask a question — response streams token by token with `▌` cursor
5. Sources expander appears after the answer
6. Clear chat resets the conversation
7. Delete a document removes it from the list
