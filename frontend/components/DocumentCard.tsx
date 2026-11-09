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
    <div className="flex items-center justify-between gap-2 py-1.5 px-2 rounded hover:bg-gray-100 dark:hover:bg-slate-800 group">
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
