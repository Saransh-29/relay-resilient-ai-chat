import { FlaskConical, PanelRight, Plus, Radio } from 'lucide-react'
import type { HealthState } from '../lib/useHealth'

interface Props {
  health: HealthState
  simulationActive: boolean
  simulationValue: string
  devOpen: boolean
  onToggleDev: () => void
  onNewChat: () => void
}

function StatusPill({ health }: { health: HealthState }) {
  const { status, data } = health
  const styles = {
    checking: { dot: 'bg-zinc-400 animate-pulse', text: 'text-zinc-300', ring: 'border-zinc-700 bg-zinc-900', label: 'Checking…' },
    online: { dot: 'bg-emerald-400', text: 'text-emerald-200', ring: 'border-emerald-500/25 bg-emerald-500/10', label: 'Connected' },
    degraded: { dot: 'bg-amber-400', text: 'text-amber-200', ring: 'border-amber-500/25 bg-amber-500/10', label: 'Degraded' },
    offline: { dot: 'bg-rose-500', text: 'text-rose-200', ring: 'border-rose-500/25 bg-rose-500/10', label: 'Offline' },
  }[status]

  const title =
    status === 'offline'
      ? health.error ?? 'Backend unreachable'
      : data
        ? `status=${data.status} · keys=${data.keys_configured} · cache=${data.cache_enabled ? 'on' : 'off'}`
        : 'Checking backend health'

  return (
    <div
      role="status"
      aria-live="polite"
      title={title}
      className={`inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-xs font-medium ${styles.ring} ${styles.text}`}
    >
      <span className="relative flex h-2 w-2">
        {status === 'online' && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-50" />}
        <span className={`relative inline-flex h-2 w-2 rounded-full ${styles.dot}`} />
      </span>
      <span>{styles.label}</span>
      {data && status !== 'offline' && (
        <span className="hidden items-center gap-2 font-mono text-[11px] text-zinc-400 sm:inline-flex">
          <span className="h-3 w-px bg-zinc-700" aria-hidden />
          <span>keys {data.keys_configured}</span>
          <span className="h-3 w-px bg-zinc-700" aria-hidden />
          <span>cache {data.cache_enabled ? 'on' : 'off'}</span>
        </span>
      )}
    </div>
  )
}

export function Header({ health, simulationActive, simulationValue, devOpen, onToggleDev, onNewChat }: Props) {
  return (
    <header className="sticky top-0 z-30 border-b border-zinc-800/80 bg-zinc-950/85 backdrop-blur supports-[backdrop-filter]:bg-zinc-950/70">
      <div className="flex h-14 items-center gap-2 px-3 sm:gap-3 sm:px-5">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 shadow-lg shadow-indigo-500/20">
            <Radio className="h-4 w-4 text-white" aria-hidden />
          </div>
          <div className="min-w-0 leading-tight max-[380px]:hidden">
            <div className="text-sm font-semibold tracking-tight text-zinc-50">Relay</div>
            <div className="hidden truncate text-[11px] text-zinc-500 sm:block">Resilient AI Chat</div>
          </div>
        </div>

        <div className="ml-1 flex min-w-0 items-center gap-2">
          <StatusPill health={health} />
          {simulationActive && (
            <button
              type="button"
              onClick={onToggleDev}
              title={`Failure simulation active: X-Simulate-Failure: ${simulationValue}`}
              className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-200 transition hover:bg-amber-500/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400"
            >
              <FlaskConical className="h-3.5 w-3.5" aria-hidden />
              <span className="sr-only sm:not-sr-only">Sim</span>
              <span className="hidden max-w-[10rem] truncate font-mono text-[11px] md:inline">{simulationValue}</span>
            </button>
          )}
        </div>

        <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
          <button
            type="button"
            onClick={onNewChat}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-zinc-800 bg-zinc-900 px-2.5 text-sm font-medium text-zinc-200 transition hover:border-zinc-700 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 sm:px-3"
            aria-label="Start a new chat"
          >
            <Plus className="h-4 w-4" aria-hidden />
            <span className="hidden sm:inline">New Chat</span>
          </button>
          <button
            type="button"
            onClick={onToggleDev}
            aria-pressed={devOpen}
            aria-controls="dev-tools"
            aria-label={devOpen ? 'Hide developer tools' : 'Show developer tools'}
            title="Developer tools"
            className={`inline-flex h-9 items-center gap-1.5 rounded-lg border px-2.5 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
              devOpen
                ? 'border-indigo-500/40 bg-indigo-500/15 text-indigo-200'
                : 'border-zinc-800 bg-zinc-900 text-zinc-300 hover:border-zinc-700 hover:bg-zinc-800'
            }`}
          >
            <PanelRight className="h-4 w-4" aria-hidden />
            <span className="hidden md:inline">Dev Tools</span>
          </button>
        </div>
      </div>
    </header>
  )
}
