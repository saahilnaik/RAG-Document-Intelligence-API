'use client'

import { useEffect, useRef } from 'react'
import { useAppStore } from '@/lib/store'
import { SourcesExpander } from './SourcesExpander'

export function ChatWindow() {
  const messages = useAppStore((s) => s.messages)
  const isStreaming = useAppStore((s) => s.isStreaming)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ behavior: 'smooth' })
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
                  : 'bg-gray-200 dark:bg-slate-700'
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
