import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, getHealth, type HealthResponse } from './api'

export type HealthStatus = 'checking' | 'online' | 'degraded' | 'offline'

export interface HealthState {
  status: HealthStatus
  data: HealthResponse | null
  error: string | null
  checkedAt: Date | null
}

const POLL_MS = 15_000

export function useHealth() {
  const [state, setState] = useState<HealthState>({ status: 'checking', data: null, error: null, checkedAt: null })
  const inflight = useRef<AbortController | null>(null)

  const check = useCallback(async () => {
    inflight.current?.abort()
    const ctrl = new AbortController()
    inflight.current = ctrl
    try {
      const data = await getHealth(ctrl.signal)
      if (ctrl.signal.aborted) return data
      setState({ status: data.status === 'ok' ? 'online' : 'degraded', data, error: null, checkedAt: new Date() })
      return data
    } catch (err) {
      if (ctrl.signal.aborted) return null
      const message = err instanceof ApiError ? err.message : String(err)
      setState((prev) => ({ status: 'offline', data: prev.data, error: message, checkedAt: new Date() }))
      return null
    }
  }, [])

  useEffect(() => {
    void check()
    const id = window.setInterval(() => {
      if (document.visibilityState === 'visible') void check()
    }, POLL_MS)
    const onVisible = () => {
      if (document.visibilityState === 'visible') void check()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      window.clearInterval(id)
      document.removeEventListener('visibilitychange', onVisible)
      inflight.current?.abort()
    }
  }, [check])

  return { ...state, refresh: check }
}
