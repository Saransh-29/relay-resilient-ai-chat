import { CopyButton } from './CopyButton'

export function JsonView({ value, maxHeight = 'max-h-64' }: { value: unknown; maxHeight?: string }) {
  const text = JSON.stringify(value, null, 2)
  return (
    <div className="relative">
      <pre
        className={`${maxHeight} overflow-auto rounded-lg border border-zinc-800 bg-zinc-950 p-3 pr-9 font-mono text-[11px] leading-relaxed text-zinc-300`}
      >
        {text}
      </pre>
      <CopyButton value={text} label="Copy JSON" className="absolute right-1.5 top-1.5" />
    </div>
  )
}
