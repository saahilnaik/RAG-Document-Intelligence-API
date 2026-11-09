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
              className="p-3 rounded-lg bg-gray-100 dark:bg-slate-800 text-sm"
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
