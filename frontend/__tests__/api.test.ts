import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fetchDocuments, uploadDocument, deleteDocument, streamAnswer } from '@/lib/api'
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
        { type: 'done' },
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
        { type: 'done' },
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

  it('calls onError when response body is null', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, body: null })
    const onError = vi.fn()
    await streamAnswer({ question: 'q', session_id: 'sid' }, vi.fn(), vi.fn(), vi.fn(), onError)
    expect(onError).toHaveBeenCalledWith('No response body from server')
  })
})
