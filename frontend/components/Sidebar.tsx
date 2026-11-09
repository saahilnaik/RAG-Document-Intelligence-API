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
    <aside className="w-64 shrink-0 flex flex-col h-full border-r border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900">
      <div className="p-4 border-b border-gray-200 dark:border-slate-700">
        <h1 className="font-semibold text-sm tracking-wide uppercase text-slate-400 dark:text-slate-400 text-gray-500">
          Documents
        </h1>
      </div>

      {/* Upload zone */}
      <div className="p-3">
        <label className="block cursor-pointer border-2 border-dashed border-gray-300 dark:border-slate-600 rounded-lg p-4 text-center text-sm text-slate-400 dark:text-slate-400 text-gray-500 hover:border-blue-500 hover:text-blue-400 transition-colors">
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
      <div className="p-3 border-t border-gray-200 dark:border-slate-700">
        <label className="block text-xs text-slate-400 dark:text-slate-400 text-gray-500 mb-1">
          Query scope
        </label>
        <select
          value={selectedDocId ?? ''}
          onChange={(e) => setSelectedDocId(e.target.value || null)}
          className="w-full text-sm rounded-lg px-2 py-1.5 bg-gray-100 dark:bg-slate-800 border border-gray-300 dark:border-slate-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
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
      <div className="p-3 border-t border-gray-200 dark:border-slate-700 flex items-center justify-between">
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
