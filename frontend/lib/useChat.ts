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
