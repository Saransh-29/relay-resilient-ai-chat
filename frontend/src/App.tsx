import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, newSessionId, sendChat } from './lib/api'
import type { ChatItem } from './lib/types'
import { useHealth } from './lib/useHealth'
import { Header } from './components/Header'
import { Composer } from './components/Composer'
import { EmptyState } from './components/EmptyState'
import { AssistantMessage, ErrorMessage, TypingIndicator, UserMessage } from './components/Messages'
import { DevPanel, type LastExchange } from './components/DevPanel'

let idCounter = 0
const uid = (p: string) => `${p}-${Date.now().toString(36)}-${(idCounter++).toString(36)}`

const DESKTOP_QUERY = '(min-width: 1024px)'
const isDesktop = () => typeof window !== 'undefined' && window.matchMedia?.(DESKTOP_QUERY).matches

export default function App() {
  // A fresh session on every page load. Never persisted.
  const [sessionId, setSessionId] = useState(newSessionId)
  const [items, setItems] = useState<ChatItem[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [last, setLast] = useState<LastExchange | null>(null)

  const [systemPrompt, setSystemPrompt] = useState('')
  const [simEnabled, setSimEnabled] = useState(false)
  const [simChoice, setSimChoice] = useState<string>('key_1=429')
  const [simCustom, setSimCustom] = useState('')
  const [devOpen, setDevOpen] = useState<boolean>(() => Boolean(isDesktop()))

  const health = useHealth()
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const bottomRef = useRef<HTMLDivElement | null>(null)
  const sessionRef = useRef(sessionId)
  const inflight = useRef<AbortController | null>(null)

  const simValue = useMemo(() => {
    if (!simEnabled) return null
    const v = simChoice === 'custom' ? simCustom.trim() : simChoice
    return v || null
  }, [simEnabled, simChoice, simCustom])

  // Auto-scroll to newest message.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [items.length, sending])

  // Escape closes the drawer on small screens.
  useEffect(() => {
    if (!devOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isDesktop()) setDevOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [devOpen])

  const dispatch = useCallback(
    async (text: string) => {
      const forSession = sessionRef.current
      const header = simValue
      const ctrl = new AbortController()
      inflight.current = ctrl
      setSending(true)
      try {
        const res = await sendChat({ sessionId: forSession, message: text, systemPrompt, simulateFailure: header }, ctrl.signal)
        if (sessionRef.current !== forSession) return
        const metadata = res.metadata
        setItems((prev) => [...prev, { id: uid('a'), kind: 'assistant', content: res.reply, metadata }])
        setLast({ metadata, simulateHeader: header, at: new Date() })
      } catch (err) {
        if (sessionRef.current !== forSession || ctrl.signal.aborted) return
        const message = err instanceof ApiError ? err.message : `Unexpected error: ${err instanceof Error ? err.message : String(err)}`
        const status = err instanceof ApiError ? err.status : null
        setItems((prev) => [...prev, { id: uid('e'), kind: 'error', message, status, retryText: text }])
      } finally {
        if (inflight.current === ctrl) {
          inflight.current = null
          setSending(false)
        }
      }
    },
    [simValue, systemPrompt],
  )

  const send = useCallback(
    (raw?: string) => {
      const text = (raw ?? input).trim()
      if (!text || sending) return
      setInput('') // clear immediately on send
      setItems((prev) => [...prev, { id: uid('u'), kind: 'user', content: text }])
      void dispatch(text)
    },
    [dispatch, input, sending],
  )

  const retry = useCallback(
    (id: string, text: string) => {
      if (sending) return
      setItems((prev) => prev.filter((it) => it.id !== id))
      void dispatch(text)
    },
    [dispatch, sending],
  )

  const restore = useCallback((id: string, text: string) => {
    setItems((prev) => prev.map((it) => (it.id === id && it.kind === 'error' ? { ...it, retried: true } : it)))
    setInput(text)
    requestAnimationFrame(() => inputRef.current?.focus())
  }, [])

  const newChat = useCallback(() => {
    inflight.current?.abort()
    inflight.current = null
    const id = newSessionId()
    sessionRef.current = id
    setSessionId(id)
    setItems([])
    setInput('')
    setSending(false)
    setLast(null)
    requestAnimationFrame(() => inputRef.current?.focus())
  }, [])

  const pickExample = useCallback(
    (prompt: string) => {
      send(prompt)
    },
    [send],
  )

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-zinc-950">
      <a
        href="#chat-input"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[60] focus:rounded-md focus:bg-indigo-600 focus:px-3 focus:py-2 focus:text-sm focus:text-white"
      >
        Skip to message input
      </a>
      <Header
        health={health}
        simulationActive={Boolean(simValue)}
        simulationValue={simValue ?? ''}
        devOpen={devOpen}
        onToggleDev={() => setDevOpen((o) => !o)}
        onNewChat={newChat}
      />

      <div className="relative flex min-h-0 flex-1">
        <main className="flex min-w-0 flex-1 flex-col" aria-label="Chat">
          <div className="relative min-h-0 flex-1 overflow-y-auto" aria-live="polite" aria-relevant="additions">
            <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-64 bg-[radial-gradient(ellipse_at_top,rgba(99,102,241,0.10),transparent_70%)]" />
            <div className="relative mx-auto flex w-full max-w-3xl flex-col gap-5 px-3 py-6 sm:px-5" data-testid="message-list">
              {items.length === 0 && !sending ? (
                <EmptyState onPick={pickExample} />
              ) : (
                items.map((it) => {
                  if (it.kind === 'user') return <UserMessage key={it.id} content={it.content} />
                  if (it.kind === 'assistant') return <AssistantMessage key={it.id} content={it.content} metadata={it.metadata} />
                  return (
                    <ErrorMessage
                      key={it.id}
                      message={it.message}
                      status={it.status}
                      retried={it.retried}
                      disabled={sending}
                      onRetry={() => retry(it.id, it.retryText)}
                      onRestore={() => restore(it.id, it.retryText)}
                    />
                  )
                })
              )}
              {sending && <TypingIndicator simulating={Boolean(simValue)} />}
              <div ref={bottomRef} className="h-px" />
            </div>
          </div>
          <Composer
            value={input}
            onChange={setInput}
            onSend={() => send()}
            sending={sending}
            inputRef={inputRef}
            simulationValue={simValue}
            hasSystemPrompt={systemPrompt.trim().length > 0}
            onOpenDev={() => setDevOpen(true)}
          />
        </main>

        {/* Backdrop for the mobile drawer */}
        <div
          aria-hidden
          onClick={() => setDevOpen(false)}
          className={`fixed inset-0 z-40 bg-black/60 backdrop-blur-[2px] transition-opacity lg:hidden ${
            devOpen ? 'opacity-100' : 'pointer-events-none opacity-0'
          }`}
        />
        <aside
          id="dev-tools"
          aria-label="Developer tools"
          className={`fixed inset-y-0 right-0 z-50 w-full max-w-[380px] border-l border-zinc-800/80 bg-zinc-950 shadow-2xl transition-transform duration-200 lg:static lg:z-auto lg:w-[380px] lg:shrink-0 lg:shadow-none lg:transition-none ${
            devOpen ? 'translate-x-0' : 'invisible translate-x-full lg:hidden'
          }`}
        >
          <DevPanel
            sessionId={sessionId}
            systemPrompt={systemPrompt}
            onSystemPromptChange={setSystemPrompt}
            simEnabled={simEnabled}
            onSimEnabledChange={setSimEnabled}
            simChoice={simChoice}
            onSimChoiceChange={setSimChoice}
            simCustom={simCustom}
            onSimCustomChange={setSimCustom}
            health={health}
            last={last}
            onClose={() => setDevOpen(false)}
          />
        </aside>
      </div>
    </div>
  )
}
