/**
 * Server state cache.
 *
 * The server is the only source of truth: every mutation replaces the cached
 * document with the response body, and a failed mutation keeps the previous
 * document untouched. Forms hold drafts locally and are only cleared after the
 * server confirms.
 */

import { useCallback, useEffect, useState } from 'react'

import { api, ApiError, type Meta, type Scenario, type StateDocument, type StateChange } from '@/lib/api'

export interface StateResource {
  state: StateDocument | null
  meta: Meta | null
  scenarios: Scenario[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  apply: (document: StateDocument) => void
  patch: (body: unknown) => Promise<StateDocument>
  reset: () => Promise<StateChange>
  applyScenario: (name: string) => Promise<StateChange>
  forget: () => void
}

export function useServerState(enabled: boolean): StateResource {
  const [state, setState] = useState<StateDocument | null>(null)
  const [meta, setMeta] = useState<Meta | null>(null)
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [document, catalogue, meta] = await Promise.all([api.state(), api.scenarios(), api.meta()])
      setState(document)
      setScenarios(catalogue.scenarios)
      setMeta(meta)
    } catch (cause) {
      if (cause instanceof ApiError && cause.isUnauthorized) {
        // Connection component owns the 401 flow; keep the view empty.
        setState(null)
        return
      }
      setError(cause instanceof Error ? cause.message : '读取状态失败')
    } finally {
      setLoading(false)
    }
  }, [])

  // No token, no request: an unauthenticated fetch would only produce 401
  // noise in the console and could be mistaken for a server error.
  useEffect(() => {
    if (enabled) void refresh()
  }, [enabled, refresh])

  const patch = useCallback(async (body: unknown) => {
    const updated = await api.patchState(body)
    setState(updated)
    return updated
  }, [])

  const reset = useCallback(async () => {
    const change = await api.reset()
    setState(change.after)
    return change
  }, [])

  const applyScenario = useCallback(async (name: string) => {
    const change = await api.applyScenario(name)
    setState(change.after)
    return change
  }, [])

  const forget = useCallback(() => {
    setState(null)
    setMeta(null)
    setScenarios([])
  }, [])

  return {
    state,
    meta,
    scenarios,
    loading,
    error,
    refresh,
    apply: setState,
    patch,
    reset,
    applyScenario,
    forget,
  }
}
