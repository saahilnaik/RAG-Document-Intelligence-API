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
