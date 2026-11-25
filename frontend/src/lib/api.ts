export type ResolutionSource = 'LIVE_INFERENCE' | 'LLM_CACHE'

export interface ChatMetadata {
  resolution_source: ResolutionSource
  model: string
  latency_ms: number
  input_tokens: number
  output_tokens: number
  key_id: string | null
  fallback_attempts: number
  [extra: string]: unknown
}

export interface ChatResponse {
  session_id: string
  reply: string
  metadata: ChatMetadata
}

export interface HealthResponse {
  status: string
  keys_configured: number
  cache_enabled: boolean
  [extra: string]: unknown
}

export interface StoredMessage {
  role: 'user' | 'assistant' | string
  content: string
  metadata?: Partial<ChatMetadata> | null
}

export interface SessionHistory {
  session_id: string
  messages: StoredMessage[]
}

declare global {
  interface Window {
    __RELAY_CONFIG__?: { API_BASE_URL?: string | null }
  }
}

/** Resolution order: runtime /config.js → VITE_API_BASE_URL → http://localhost:8000 */
export function resolveApiBase(): string {
  const candidates = [
    typeof window !== 'undefined' ? window.__RELAY_CONFIG__?.API_BASE_URL : undefined,
    import.meta.env.VITE_API_BASE_URL as string | undefined,
    'http://localhost:8000',
  ]
  const picked = candidates.find((v) => typeof v === 'string' && v.trim() !== '') as string
  return picked.trim().replace(/\/+$/, '')
}

export const API_BASE = resolveApiBase()

export type ApiErrorKind = 'network' | 'validation' | 'unavailable' | 'not_found' | 'http' | 'parse'

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number | null
  readonly body: unknown

  constructor(kind: ApiErrorKind, message: string, status: number | null = null, body: unknown = null) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
    this.body = body
  }
}

interface ValidationItem {
  loc?: unknown[]
  msg?: string
  type?: string
}

/** Turn a FastAPI `detail` (string | array | object) into readable text. */
export function formatDetail(detail: unknown): string | null {
  if (detail == null) return null
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const parts = detail.map((item: ValidationItem | unknown) => {
      if (item && typeof item === 'object') {
        const it = item as ValidationItem
        const loc = Array.isArray(it.loc) ? it.loc.filter((p) => p !== 'body').join('.') : ''
        const msg = it.msg ?? JSON.stringify(item)
        return loc ? `${loc}: ${msg}` : msg
      }
      return String(item)
    })
    return parts.join('; ')
  }
  if (typeof detail === 'object') {
    const d = detail as Record<string, unknown>
    if (typeof d.message === 'string') return d.message
    if (typeof d.msg === 'string') return d.msg
    return JSON.stringify(detail)
  }
  return String(detail)
}

function messageFor(status: number, detailText: string | null): { kind: ApiErrorKind; message: string } {
  if (status === 422 || status === 400) {
    return { kind: 'validation', message: `Validation error: ${detailText ?? 'the request was rejected.'}` }
  }
  if (status === 503) {
    const suffix = detailText ? ` (${detailText})` : ''
    return {
      kind: 'unavailable',
      message: `All providers are unavailable right now. Every API key failed or is rate-limited. Please try again shortly.${suffix}`,
    }
  }
  if (status === 404) {
    return { kind: 'not_found', message: detailText ?? 'Not found.' }
  }
  if (status === 429) {
    return { kind: 'http', message: `Rate limited (429): ${detailText ?? 'too many requests.'}` }
  }
  if (status >= 500) {
    return { kind: 'http', message: `Server error (${status}): ${detailText ?? 'the backend failed to process the request.'}` }
  }
  return { kind: 'http', message: `Request failed (${status}): ${detailText ?? 'unexpected response.'}` }
}

interface RequestOptions {
  method?: 'GET' | 'POST'
  body?: unknown
  headers?: Record<string, string>
  signal?: AbortSignal
  timeoutMs?: number
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const url = `${API_BASE}${path}`
  const controller = new AbortController()
  const timeoutMs = opts.timeoutMs ?? 90_000
  const timer = setTimeout(() => controller.abort(new DOMException('timeout', 'TimeoutError')), timeoutMs)
  const onAbort = () => controller.abort(opts.signal?.reason)
  opts.signal?.addEventListener('abort', onAbort)

  let res: Response
  try {
    res = await fetch(url, {
      method: opts.method ?? 'GET',
      headers: {
        Accept: 'application/json',
        ...(opts.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...opts.headers,
      },
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: controller.signal,
    })
  } catch (err) {
    const timedOut = err instanceof DOMException && (err.name === 'TimeoutError' || controller.signal.reason?.name === 'TimeoutError')
    throw new ApiError(
      'network',
      timedOut
        ? `Request to ${API_BASE} timed out after ${Math.round(timeoutMs / 1000)}s.`
        : `Can't reach backend at ${API_BASE}. Check that the server is running and CORS allows this origin.`,
    )
  } finally {
    clearTimeout(timer)
    opts.signal?.removeEventListener('abort', onAbort)
  }

  const text = await res.text().catch(() => '')
  let data: unknown = null
  let parsed = false
  if (text) {
    try {
      data = JSON.parse(text)
      parsed = true
    } catch {
      parsed = false
    }
  }

  if (!res.ok) {
    const detailText = parsed
      ? formatDetail((data as { detail?: unknown } | null)?.detail) ?? formatDetail(data)
      : text
        ? `non-JSON response: ${text.slice(0, 160).replace(/\s+/g, ' ').trim()}`
        : res.statusText || null
    const { kind, message } = messageFor(res.status, detailText)
    throw new ApiError(kind, message, res.status, parsed ? data : text)
  }

  if (!parsed) {
    throw new ApiError(
      'parse',
      `Backend returned an unreadable response (expected JSON, got ${text ? `"${text.slice(0, 80)}…"` : 'an empty body'}).`,
      res.status,
      text,
    )
  }
  return data as T
}

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>('/health', { signal, timeoutMs: 8_000 })
}

export interface SendChatInput {
  sessionId: string
  message: string
  systemPrompt?: string
  simulateFailure?: string | null
}

export function sendChat(input: SendChatInput, signal?: AbortSignal): Promise<ChatResponse> {
  const body: Record<string, string> = { session_id: input.sessionId, message: input.message }
  if (input.systemPrompt && input.systemPrompt.trim()) body.system_prompt = input.systemPrompt
  const headers: Record<string, string> = {}
  if (input.simulateFailure && input.simulateFailure.trim()) {
    headers['X-Simulate-Failure'] = input.simulateFailure.trim()
  }
  return request<ChatResponse>('/chat', { method: 'POST', body, headers, signal })
}

/** 404 for a brand-new session is treated as an empty history. */
export async function getSessionMessages(sessionId: string, signal?: AbortSignal): Promise<SessionHistory> {
  try {
    return await request<SessionHistory>(`/sessions/${encodeURIComponent(sessionId)}/messages`, { signal, timeoutMs: 15_000 })
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      return { session_id: sessionId, messages: [] }
    }
    throw err
  }
}

export function newSessionId(): string {
  const uuid =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`
  return `s-${uuid.replace(/-/g, '').slice(0, 16)}`
}
