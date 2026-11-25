import { useState, type ReactNode } from 'react'
import {
  Activity,
  ChevronDown,
  FlaskConical,
  Fingerprint,
  History,
  Loader2,
  RefreshCw,
  ScrollText,
  Server,
  X,
} from 'lucide-react'
import { API_BASE, ApiError, getSessionMessages, type ChatMetadata, type SessionHistory } from '../lib/api'
import type { HealthState } from '../lib/useHealth'
import { FAILURE_PRESETS } from '../lib/types'
import { CopyButton } from './CopyButton'
import { JsonView } from './JsonView'

export interface LastExchange {
  metadata: ChatMetadata
  simulateHeader: string | null
  at: Date
}

interface Props {
  sessionId: string
  systemPrompt: string
  onSystemPromptChange: (v: string) => void
  simEnabled: boolean
  onSimEnabledChange: (v: boolean) => void
  simChoice: string
  onSimChoiceChange: (v: string) => void
  simCustom: string
  onSimCustomChange: (v: string) => void
  health: HealthState & { refresh: () => Promise<unknown> }
  last: LastExchange | null
  onClose: () => void
}

function Section({
  icon,
  title,
  badge,
  defaultOpen = true,
  children,
}: {
  icon: ReactNode
  title: string
  badge?: ReactNode
  defaultOpen?: boolean
  children: ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <section className="border-b border-zinc-800/80">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-4 py-3 text-left text-[13px] font-medium text-zinc-200 transition hover:bg-zinc-900/60 focus-visible:bg-zinc-900 focus-visible:outline-none"
      >
        <span className="text-zinc-500">{icon}</span>
        <span className="flex-1">{title}</span>
        {badge}
        <ChevronDown className={`h-4 w-4 text-zinc-500 transition-transform ${open ? '' : '-rotate-90'}`} aria-hidden />
      </button>
      {open && <div className="space-y-3 px-4 pb-4">{children}</div>}
    </section>
  )
}

const btn =
  'inline-flex items-center gap-1.5 rounded-md border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-xs font-medium text-zinc-200 transition hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 disabled:cursor-not-allowed disabled:opacity-50'

export function DevPanel(props: Props) {
  const { sessionId, health, last } = props
  const [inspect, setInspect] = useState<{ loading: boolean; data: SessionHistory | null; error: string | null }>({
    loading: false,
    data: null,
    error: null,
  })
  const [healthLoading, setHealthLoading] = useState(false)

  const effectiveSim = props.simChoice === 'custom' ? props.simCustom.trim() : props.simChoice
  const simActive = props.simEnabled && effectiveSim.length > 0

  async function loadSession() {
    setInspect({ loading: true, data: null, error: null })
    try {
      const data = await getSessionMessages(sessionId)
      setInspect({ loading: false, data, error: null })
    } catch (err) {
      setInspect({ loading: false, data: null, error: err instanceof ApiError ? err.message : String(err) })
    }
  }

  async function runHealth() {
    setHealthLoading(true)
    try {
      await health.refresh()
    } finally {
      setHealthLoading(false)
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 shrink-0 items-center gap-2 border-b border-zinc-800/80 px-4">
        <h2 className="flex-1 text-sm font-semibold text-zinc-100">Developer Tools</h2>
        <button
          type="button"
          onClick={props.onClose}
          aria-label="Close developer tools"
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-zinc-400 transition hover:bg-zinc-800 hover:text-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
        >
          <X className="h-4 w-4" aria-hidden />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {/* System prompt */}
        <Section
          icon={<ScrollText className="h-4 w-4" />}
          title="System prompt"
          badge={
            props.systemPrompt.trim() ? (
              <span className="rounded bg-indigo-500/15 px-1.5 py-px font-mono text-[10px] text-indigo-300">set</span>
            ) : null
          }
        >
          <label htmlFor="system-prompt" className="block text-xs text-zinc-400">
            Sent as <code className="font-mono text-zinc-300">system_prompt</code> with each request when non-empty. Overrides the
            default for this session.
          </label>
          <textarea
            id="system-prompt"
            data-testid="system-prompt-input"
            value={props.systemPrompt}
            onChange={(e) => props.onSystemPromptChange(e.target.value)}
            rows={4}
            placeholder="e.g. You are a concise assistant. Answer in one sentence."
            className="w-full resize-y rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-indigo-500/60 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
          />
        </Section>

        {/* Failure simulation */}
        <Section
          icon={<FlaskConical className="h-4 w-4" />}
          title="Failure simulation"
          badge={
            simActive ? (
              <span className="rounded bg-amber-500/15 px-1.5 py-px font-mono text-[10px] text-amber-300">ON</span>
            ) : null
          }
        >
          <label className="flex cursor-pointer items-center gap-2.5 text-sm text-zinc-200">
            <input
              type="checkbox"
              data-testid="simulate-failure-toggle"
              checked={props.simEnabled}
              onChange={(e) => props.onSimEnabledChange(e.target.checked)}
              className="h-4 w-4 rounded border-zinc-600 bg-zinc-900 accent-amber-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400"
            />
            Send <code className="font-mono text-xs text-amber-200">X-Simulate-Failure</code> header
          </label>
          <fieldset className="space-y-2" disabled={!props.simEnabled}>
            <legend className="sr-only">Failure preset</legend>
            <div className="flex flex-wrap gap-1.5">
              {[...FAILURE_PRESETS, 'custom'].map((p) => {
                const selected = props.simChoice === p
                return (
                  <button
                    key={p}
                    type="button"
                    onClick={() => props.onSimChoiceChange(p)}
                    aria-pressed={selected}
                    className={`rounded-md border px-2 py-1 font-mono text-[11px] transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 disabled:cursor-not-allowed disabled:opacity-40 ${
                      selected
                        ? 'border-amber-500/50 bg-amber-500/15 text-amber-200'
                        : 'border-zinc-800 bg-zinc-900 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200'
                    }`}
                  >
                    {p}
                  </button>
                )
              })}
            </div>
            {props.simChoice === 'custom' && (
              <input
                type="text"
                aria-label="Custom X-Simulate-Failure value"
                value={props.simCustom}
                onChange={(e) => props.onSimCustomChange(e.target.value)}
                placeholder="key_2=503"
                spellCheck={false}
                className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-1.5 font-mono text-xs text-zinc-100 placeholder:text-zinc-600 focus:border-amber-500/60 focus:outline-none focus:ring-2 focus:ring-amber-500/20 disabled:opacity-50"
              />
            )}
          </fieldset>
          <p className={`rounded-md border px-2.5 py-2 text-[11.5px] leading-snug ${simActive ? 'border-amber-500/30 bg-amber-500/10 text-amber-200' : 'border-zinc-800 bg-zinc-900/60 text-zinc-500'}`}>
            {simActive ? (
              <>
                Next requests will send <code className="font-mono">X-Simulate-Failure: {effectiveSim}</code>. Simulated requests bypass the
                cache, so the failover path really runs. The backend honors this header only when <code className="font-mono">ENABLE_FAILURE_SIMULATION=true</code>.
              </>
            ) : (
              'Off. Requests are sent normally.'
            )}
          </p>
        </Section>

        {/* Health */}
        <Section
          icon={<Activity className="h-4 w-4" />}
          title="Backend health"
          badge={
            <span
              className={`rounded px-1.5 py-px font-mono text-[10px] ${
                health.status === 'online'
                  ? 'bg-emerald-500/15 text-emerald-300'
                  : health.status === 'offline'
                    ? 'bg-rose-500/15 text-rose-300'
                    : 'bg-zinc-800 text-zinc-400'
              }`}
            >
              {health.status}
            </span>
          }
        >
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <Server className="h-3.5 w-3.5 shrink-0 text-zinc-500" aria-hidden />
            <span className="min-w-0 flex-1 truncate font-mono text-zinc-300" title={API_BASE}>
              {API_BASE}
            </span>
            <CopyButton value={API_BASE} label="Copy API base URL" />
          </div>
          <div className="flex items-center gap-2">
            <button type="button" onClick={runHealth} disabled={healthLoading} className={btn} data-testid="health-check-button">
              {healthLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <RefreshCw className="h-3.5 w-3.5" aria-hidden />}
              GET /health
            </button>
            {health.checkedAt && (
              <span className="font-mono text-[10.5px] text-zinc-600">checked {health.checkedAt.toLocaleTimeString()}</span>
            )}
          </div>
          {health.status === 'offline' && health.error && (
            <p className="rounded-md border border-rose-500/30 bg-rose-500/10 px-2.5 py-2 text-xs text-rose-200">{health.error}</p>
          )}
          {health.data && <JsonView value={health.data} maxHeight="max-h-40" />}
        </Section>

        {/* Session */}
        <Section icon={<Fingerprint className="h-4 w-4" />} title="Session">
          <div className="flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-1.5">
            <span className="text-[11px] text-zinc-500">id</span>
            <span data-testid="session-id" className="min-w-0 flex-1 truncate font-mono text-xs text-zinc-200" title={sessionId}>
              {sessionId}
            </span>
            <CopyButton value={sessionId} label="Copy session id" />
          </div>
          <button type="button" onClick={loadSession} disabled={inspect.loading} className={btn}>
            {inspect.loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <History className="h-3.5 w-3.5" aria-hidden />}
            GET /sessions/&#123;id&#125;/messages
          </button>
          {inspect.error && (
            <p className="rounded-md border border-rose-500/30 bg-rose-500/10 px-2.5 py-2 text-xs text-rose-200">{inspect.error}</p>
          )}
          {inspect.data && (
            <>
              <p className="font-mono text-[11px] text-zinc-500">
                {inspect.data.messages.length === 0
                  ? 'No stored messages yet (new session).'
                  : `${inspect.data.messages.length} stored message(s), oldest first`}
              </p>
              <JsonView value={inspect.data} maxHeight="max-h-80" />
            </>
          )}
        </Section>

        {/* Last response */}
        <Section icon={<Server className="h-4 w-4" />} title="Last response metadata">
          {last ? (
            <>
              <p className="font-mono text-[11px] text-zinc-500">
                {last.at.toLocaleTimeString()}
                {last.simulateHeader ? ` · X-Simulate-Failure: ${last.simulateHeader}` : ' · no simulation header'}
              </p>
              <JsonView value={last.metadata} />
            </>
          ) : (
            <p className="text-xs text-zinc-500">No successful response yet.</p>
          )}
        </Section>
      </div>
    </div>
  )
}
