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
