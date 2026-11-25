import { useLayoutEffect, type KeyboardEvent, type RefObject } from 'react'
import { ArrowUp, FlaskConical, Loader2, ScrollText } from 'lucide-react'

export const MAX_MESSAGE_CHARS = 4000

interface Props {
  value: string
  onChange: (v: string) => void
  onSend: () => void
  sending: boolean
  inputRef: RefObject<HTMLTextAreaElement>
  simulationValue: string | null
  hasSystemPrompt: boolean
  onOpenDev: () => void
}

export function Composer({ value, onChange, onSend, sending, inputRef, simulationValue, hasSystemPrompt, onOpenDev }: Props) {
  const trimmed = value.trim()
  const tooLong = trimmed.length > MAX_MESSAGE_CHARS
  const canSend = !sending && trimmed.length > 0

  // Auto-grow the textarea up to a max height.
  useLayoutEffect(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [value, inputRef])

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      if (canSend) onSend()
    }
  }

  return (
    <div className="border-t border-zinc-800/80 bg-zinc-950/90 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 backdrop-blur sm:px-5">
      <div className="mx-auto w-full max-w-3xl">
        {(simulationValue || hasSystemPrompt) && (
          <div className="mb-2 flex flex-wrap gap-2">
            {simulationValue && (
              <button
                type="button"
                onClick={onOpenDev}
                className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 font-mono text-[11px] text-amber-200 hover:bg-amber-500/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400"
              >
                <FlaskConical className="h-3 w-3 shrink-0" aria-hidden />
                <span className="truncate">X-Simulate-Failure: {simulationValue}</span>
              </button>
            )}
            {hasSystemPrompt && (
              <button
                type="button"
                onClick={onOpenDev}
                className="inline-flex items-center gap-1.5 rounded-md border border-indigo-500/30 bg-indigo-500/10 px-2 py-0.5 font-mono text-[11px] text-indigo-200 hover:bg-indigo-500/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              >
                <ScrollText className="h-3 w-3" aria-hidden />
                custom system prompt
              </button>
            )}
          </div>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (canSend) onSend()
          }}
          className="relative flex items-end gap-2 rounded-2xl border border-zinc-800 bg-zinc-900 p-2 shadow-xl shadow-black/30 transition focus-within:border-indigo-500/60 focus-within:ring-2 focus-within:ring-indigo-500/20"
        >
          <label htmlFor="chat-input" className="sr-only">
            Message
          </label>
          <textarea
            id="chat-input"
            ref={inputRef}
            data-testid="chat-input"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={onKeyDown}
            rows={1}
            placeholder="Message Relay…"
            autoComplete="off"
            spellCheck
            aria-describedby="composer-hint"
            className="max-h-[200px] min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2 text-[0.95rem] leading-6 text-zinc-100 placeholder:text-zinc-500 focus:outline-none"
          />
          <button
            type="submit"
            data-testid="send-button"
            disabled={!canSend}
            aria-label={sending ? 'Sending' : 'Send message'}
            className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-md shadow-indigo-900/40 transition hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-900 disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-500 disabled:shadow-none"
          >
            {sending ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <ArrowUp className="h-4 w-4" aria-hidden />}
          </button>
        </form>
        <div id="composer-hint" className="mt-1.5 flex items-center justify-between px-1 font-mono text-[10.5px] text-zinc-600">
          <span className="hidden sm:inline">
            <kbd className="rounded border border-zinc-800 px-1">Enter</kbd> to send &middot;{' '}
            <kbd className="rounded border border-zinc-800 px-1">Shift</kbd>+<kbd className="rounded border border-zinc-800 px-1">Enter</kbd> newline
          </span>
          <span className="sm:hidden">Enter to send</span>
          <span className={tooLong ? 'text-rose-400' : trimmed.length > MAX_MESSAGE_CHARS * 0.9 ? 'text-amber-400' : ''}>
            {trimmed.length}/{MAX_MESSAGE_CHARS}
          </span>
        </div>
      </div>
    </div>
  )
}
