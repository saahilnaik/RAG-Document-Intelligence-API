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
        <header className="px-6 py-3 border-b border-gray-200 dark:border-slate-700 shrink-0">
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
