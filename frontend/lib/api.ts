import type { DocumentStatus, SourceChunk, UploadResponse } from '@/types'

const API_URL =
  (typeof process !== 'undefined' && process.env.NEXT_PUBLIC_API_URL) ||
  'http://localhost:8000'

// Dev/demo convenience: NEXT_PUBLIC_* values ship to the browser, so this is NOT
// a secret. For real deployments put the app behind a login / BFF proxy that
// injects the key server-side.
const API_KEY = (typeof process !== 'undefined' && process.env.NEXT_PUBLIC_API_KEY) || ''

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  return API_KEY ? { ...extra, 'X-API-Key': API_KEY } : extra
}

export async function fetchDocuments(): Promise<DocumentStatus[]> {
  try {
    const res = await fetch(`${API_URL}/documents`, { headers: authHeaders() })
    if (!res.ok) return []
    return res.json()
  } catch {
    return []
  }
}

export async function uploadDocument(file: File): Promise<UploadResponse> {
  const body = new FormData()
  body.append('file', file)
  const res = await fetch(`${API_URL}/upload`, { method: 'POST', body, headers: authHeaders() })
  if (!res.ok) {
    throw new Error(`Upload failed: ${res.status}`)
  }
  return res.json()
}

export async function deleteDocument(docId: string): Promise<void> {
  try {
    await fetch(`${API_URL}/documents/${docId}`, { method: 'DELETE', headers: authHeaders() })
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
  let response: Response
  try {
    response = await fetch(`${API_URL}/ask/stream`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
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

  try {
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
          if (event.type === 'token' && typeof event.data === 'string') onToken(event.data)
          else if (event.type === 'sources' && Array.isArray(event.data)) onSources(event.data as SourceChunk[])
          else if (event.type === 'done') onDone()
          else if (event.type === 'error' && typeof event.data === 'string') onError(event.data)
        } catch {
          // malformed SSE line — skip
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}
