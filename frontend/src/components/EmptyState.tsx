import { Database, MessagesSquare, Shuffle, Sparkles } from 'lucide-react'

const EXAMPLES = [
  { title: 'Quick fact', prompt: 'What is the capital of France?' },
  { title: 'Explain a concept', prompt: 'Explain API key failover in two short paragraphs.' },
  { title: 'Write code', prompt: 'Write a Python function that retries a request with exponential backoff.' },
  { title: 'Test memory', prompt: 'My name is Ada and my favourite language is Rust. Remember that.' },
]

const FEATURES = [
  { icon: Shuffle, label: 'Key failover', text: '429 / 5xx on one key? The next key answers.' },
  { icon: Database, label: 'Response cache', text: 'Repeat a first message to see LLM_CACHE.' },
  { icon: MessagesSquare, label: 'Multi-turn', text: 'History is kept server-side per session.' },
]

export function EmptyState({ onPick }: { onPick: (prompt: string) => void }) {
  return (
    <div className="mx-auto flex w-full max-w-3xl animate-fade-up flex-col items-center px-1 py-8 text-center sm:py-14">
      <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 shadow-xl shadow-indigo-500/25">
        <Sparkles className="h-6 w-6 text-white" aria-hidden />
      </div>
      <h1 className="text-xl font-semibold tracking-tight text-zinc-50 sm:text-2xl">How can I help today?</h1>
      <p className="mt-2 max-w-md text-sm text-zinc-400">
        Every reply shows where it came from, which key answered, how long it took and the tokens it used.
      </p>

      <div className="mt-7 grid w-full grid-cols-1 gap-2.5 sm:grid-cols-2">
        {EXAMPLES.map((ex) => (
          <button
            key={ex.prompt}
            type="button"
            onClick={() => onPick(ex.prompt)}
            className="group rounded-xl border border-zinc-800 bg-zinc-900/60 p-3.5 text-left transition hover:-translate-y-px hover:border-indigo-500/40 hover:bg-zinc-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
          >
            <div className="text-xs font-medium text-indigo-300">{ex.title}</div>
            <div className="mt-1 text-sm text-zinc-300 group-hover:text-zinc-100">{ex.prompt}</div>
          </button>
        ))}
      </div>

      <div className="mt-6 grid w-full grid-cols-1 gap-2 sm:grid-cols-3">
        {FEATURES.map(({ icon: Icon, label, text }) => (
          <div key={label} className="flex items-start gap-2.5 rounded-lg border border-zinc-800/60 px-3 py-2.5 text-left">
            <Icon className="mt-0.5 h-4 w-4 shrink-0 text-zinc-500" aria-hidden />
            <div>
              <div className="text-xs font-medium text-zinc-300">{label}</div>
              <div className="text-[11.5px] leading-snug text-zinc-500">{text}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
