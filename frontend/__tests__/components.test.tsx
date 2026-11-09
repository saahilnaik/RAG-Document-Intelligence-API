import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { useAppStore } from '@/lib/store'

beforeEach(() => {
  useAppStore.setState({
    messages: [],
    sessionId: 'test-session',
    isStreaming: false,
    documents: [],
    selectedDocId: null,
    isPolling: false,
    theme: 'dark',
  })
  document.documentElement.className = ''
})

describe('ThemeProvider', () => {
  it('adds dark class to html element when theme is dark', async () => {
    const { ThemeProvider } = await import('@/components/ThemeProvider')
    render(<ThemeProvider><div /></ThemeProvider>)
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('removes dark class when theme is light', async () => {
    useAppStore.setState({ theme: 'light' })
    const { ThemeProvider } = await import('@/components/ThemeProvider')
    render(<ThemeProvider><div /></ThemeProvider>)
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })
})

describe('ThemeToggle', () => {
  it('renders a button', async () => {
    const { ThemeToggle } = await import('@/components/ThemeToggle')
    render(<ThemeToggle />)
    expect(screen.getByRole('button')).toBeInTheDocument()
  })

  it('calls toggleTheme when clicked', async () => {
    const { ThemeToggle } = await import('@/components/ThemeToggle')
    render(<ThemeToggle />)
    fireEvent.click(screen.getByRole('button'))
    expect(useAppStore.getState().theme).toBe('light')
  })
})

describe('DocumentCard', () => {
  const onDelete = vi.fn()

  it('renders filename', async () => {
    const { DocumentCard } = await import('@/components/DocumentCard')
    render(
      <DocumentCard
        doc={{ doc_id: 'd1', filename: 'report.pdf', status: 'ready', created_at: '', chunk_count: 5 }}
        onDelete={onDelete}
      />
    )
    expect(screen.getByText(/report\.pdf/)).toBeInTheDocument()
  })

  it('shows chunk count when ready', async () => {
    const { DocumentCard } = await import('@/components/DocumentCard')
    render(
      <DocumentCard
        doc={{ doc_id: 'd1', filename: 'doc.pdf', status: 'ready', created_at: '', chunk_count: 12 }}
        onDelete={onDelete}
      />
    )
    expect(screen.getByText(/12 chunks/)).toBeInTheDocument()
  })

  it('calls onDelete when delete button clicked', async () => {
    const { DocumentCard } = await import('@/components/DocumentCard')
    render(
      <DocumentCard
        doc={{ doc_id: 'd1', filename: 'doc.pdf', status: 'ready', created_at: '' }}
        onDelete={onDelete}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /delete/i }))
    expect(onDelete).toHaveBeenCalledWith('d1')
  })

  it('shows processing indicator for processing status', async () => {
    const { DocumentCard } = await import('@/components/DocumentCard')
    render(
      <DocumentCard
        doc={{ doc_id: 'd1', filename: 'doc.pdf', status: 'processing', created_at: '' }}
        onDelete={onDelete}
      />
    )
    expect(screen.getByText(/processing/i)).toBeInTheDocument()
  })
})

describe('SourcesExpander', () => {
  const sources: import('@/types').SourceChunk[] = [
    { doc_id: 'd1', filename: 'report.pdf', page_number: 3, text: 'some text here', score: 0.92 },
    { doc_id: 'd2', filename: 'notes.txt', text: 'other text', score: 0.85 },
  ]

  it('renders a toggle button with source count', async () => {
    const { SourcesExpander } = await import('@/components/SourcesExpander')
    render(<SourcesExpander sources={sources} />)
    expect(screen.getByText(/2 sources/i)).toBeInTheDocument()
  })

  it('hides source details by default', async () => {
    const { SourcesExpander } = await import('@/components/SourcesExpander')
    render(<SourcesExpander sources={sources} />)
    expect(screen.queryByText('some text here')).not.toBeInTheDocument()
  })

  it('shows source details after clicking toggle', async () => {
    const { SourcesExpander } = await import('@/components/SourcesExpander')
    render(<SourcesExpander sources={sources} />)
    fireEvent.click(screen.getByText(/2 sources/i))
    expect(screen.getByText('some text here')).toBeInTheDocument()
    expect(screen.getByText(/report\.pdf/)).toBeInTheDocument()
  })

  it('shows singular label for one source', async () => {
    const { SourcesExpander } = await import('@/components/SourcesExpander')
    render(<SourcesExpander sources={[sources[0]]} />)
    expect(screen.getByText(/1 source/i)).toBeInTheDocument()
    expect(screen.queryByText(/1 sources/i)).not.toBeInTheDocument()
  })
})

describe('Sidebar', () => {
  beforeEach(() => {
    vi.mock('@/lib/api', () => ({
      fetchDocuments: vi.fn().mockResolvedValue([]),
      uploadDocument: vi.fn(),
      deleteDocument: vi.fn(),
      streamAnswer: vi.fn(),
    }))
    useAppStore.setState({
      messages: [],
      sessionId: 'sid',
      isStreaming: false,
      documents: [
        { doc_id: 'd1', filename: 'report.pdf', status: 'ready', created_at: '', chunk_count: 5 },
      ],
      selectedDocId: null,
      isPolling: false,
      theme: 'dark',
    })
  })

  it('renders the document list from the store', async () => {
    const { Sidebar } = await import('@/components/Sidebar')
    render(<Sidebar />)
    expect(screen.getAllByText(/report\.pdf/)[0]).toBeInTheDocument()
  })

  it('renders the scope selector with all-docs option', async () => {
    const { Sidebar } = await import('@/components/Sidebar')
    render(<Sidebar />)
    expect(screen.getByText(/All documents/i)).toBeInTheDocument()
  })

  it('renders a clear chat button', async () => {
    const { Sidebar } = await import('@/components/Sidebar')
    render(<Sidebar />)
    expect(screen.getByText(/clear chat/i)).toBeInTheDocument()
  })
})

describe('ChatInput', () => {
  it('renders a text input and send button', async () => {
    const { ChatInput } = await import('@/components/ChatInput')
    render(<ChatInput onSend={vi.fn()} />)
    expect(screen.getByPlaceholderText(/ask a question/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /send/i })).toBeInTheDocument()
  })

  it('calls onSend with trimmed input on button click', async () => {
    const { ChatInput } = await import('@/components/ChatInput')
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)
    const input = screen.getByPlaceholderText(/ask a question/i)
    fireEvent.change(input, { target: { value: '  hello  ' } })
    fireEvent.click(screen.getByRole('button', { name: /send/i }))
    expect(onSend).toHaveBeenCalledWith('hello')
  })

  it('clears input after sending', async () => {
    const { ChatInput } = await import('@/components/ChatInput')
    render(<ChatInput onSend={vi.fn()} />)
    const input = screen.getByPlaceholderText(/ask a question/i) as HTMLInputElement
    fireEvent.change(input, { target: { value: 'hello' } })
    fireEvent.click(screen.getByRole('button', { name: /send/i }))
    expect(input.value).toBe('')
  })

  it('does not call onSend for empty input', async () => {
    const { ChatInput } = await import('@/components/ChatInput')
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)
    fireEvent.click(screen.getByRole('button', { name: /send/i }))
    expect(onSend).not.toHaveBeenCalled()
  })

  it('disables the button when disabled prop is true', async () => {
    const { ChatInput } = await import('@/components/ChatInput')
    render(<ChatInput onSend={vi.fn()} disabled />)
    expect(screen.getByRole('button', { name: /send/i })).toBeDisabled()
  })
})

describe('ChatWindow', () => {
  it('renders empty state when no messages', async () => {
    const { ChatWindow } = await import('@/components/ChatWindow')
    render(<ChatWindow />)
    expect(screen.getByText(/upload a document/i)).toBeInTheDocument()
  })

  it('renders user and assistant messages', async () => {
    useAppStore.setState({
      ...useAppStore.getState(),
      messages: [
        { id: '1', role: 'user', content: 'What is RAG?' },
        { id: '2', role: 'assistant', content: 'RAG stands for Retrieval-Augmented Generation.' },
      ],
    })
    const { ChatWindow } = await import('@/components/ChatWindow')
    render(<ChatWindow />)
    expect(screen.getByText('What is RAG?')).toBeInTheDocument()
    expect(screen.getByText(/Retrieval-Augmented Generation/)).toBeInTheDocument()
  })

  it('shows streaming cursor when isStreaming is true', async () => {
    useAppStore.setState({
      ...useAppStore.getState(),
      isStreaming: true,
      messages: [{ id: '1', role: 'assistant', content: 'Partial answer' }],
    })
    const { ChatWindow } = await import('@/components/ChatWindow')
    render(<ChatWindow />)
    expect(screen.getByText(/▌/)).toBeInTheDocument()
  })
})
