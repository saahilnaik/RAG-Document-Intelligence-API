import { describe, it, expect, beforeEach } from 'vitest'
import { useAppStore } from '@/lib/store'
import type { DocumentStatus, SourceChunk } from '@/types'

const resetStore = () =>
  useAppStore.setState({
    messages: [],
    sessionId: 'test-session',
    isStreaming: false,
    documents: [],
    selectedDocId: null,
    isPolling: false,
    theme: 'dark',
  })

beforeEach(resetStore)

describe('addMessage', () => {
  it('appends a user message', () => {
    useAppStore.getState().addMessage({ id: '1', role: 'user', content: 'hello' })
    expect(useAppStore.getState().messages).toHaveLength(1)
    expect(useAppStore.getState().messages[0].content).toBe('hello')
  })
})

describe('appendToken', () => {
  it('appends a token to the last assistant message', () => {
    useAppStore.getState().addMessage({ id: '1', role: 'assistant', content: '' })
    useAppStore.getState().appendToken('Hi')
    useAppStore.getState().appendToken('!')
    expect(useAppStore.getState().messages[0].content).toBe('Hi!')
  })

  it('does not modify user messages', () => {
    useAppStore.getState().addMessage({ id: '1', role: 'user', content: 'question' })
    useAppStore.getState().appendToken('ignored')
    expect(useAppStore.getState().messages[0].content).toBe('question')
  })
})

describe('setMessageSources', () => {
  it('attaches sources to the correct message by id', () => {
    useAppStore.getState().addMessage({ id: 'msg-1', role: 'assistant', content: 'answer' })
    const sources: SourceChunk[] = [
      { doc_id: 'd1', filename: 'a.pdf', text: 'chunk text', score: 0.9 },
    ]
    useAppStore.getState().setMessageSources('msg-1', sources)
    expect(useAppStore.getState().messages[0].sources).toEqual(sources)
  })
})

describe('setStreamingError', () => {
  it('replaces last assistant message content with error text', () => {
    useAppStore.getState().addMessage({ id: '1', role: 'assistant', content: '' })
    useAppStore.getState().setStreamingError('timeout')
    expect(useAppStore.getState().messages[0].content).toBe('Error: timeout')
    expect(useAppStore.getState().isStreaming).toBe(false)
  })
})

describe('clearChat', () => {
  it('clears messages and generates a new session id', () => {
    useAppStore.getState().addMessage({ id: '1', role: 'user', content: 'hi' })
    const oldSession = useAppStore.getState().sessionId
    useAppStore.getState().clearChat()
    expect(useAppStore.getState().messages).toHaveLength(0)
    expect(useAppStore.getState().sessionId).not.toBe(oldSession)
  })
})

describe('toggleTheme', () => {
  it('switches from dark to light', () => {
    expect(useAppStore.getState().theme).toBe('dark')
    useAppStore.getState().toggleTheme()
    expect(useAppStore.getState().theme).toBe('light')
  })

  it('switches from light to dark', () => {
    useAppStore.setState({ theme: 'light' })
    useAppStore.getState().toggleTheme()
    expect(useAppStore.getState().theme).toBe('dark')
  })
})

describe('setDocuments', () => {
  it('replaces the documents list', () => {
    const docs: DocumentStatus[] = [
      { doc_id: 'd1', filename: 'a.pdf', status: 'ready', created_at: '' },
    ]
    useAppStore.getState().setDocuments(docs)
    expect(useAppStore.getState().documents).toEqual(docs)
  })
})
