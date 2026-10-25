/**
 * Server state cache.
 *
 * The server is the only source of truth: every mutation replaces the cached
 * document with the response body, and a failed mutation keeps the previous
 * document untouched. Forms hold drafts locally and are only cleared after the
 * server confirms.
 *
 * The hook also tracks which scenario (if any) produced the current state. The
 * server deliberately does not store "current scenario" — a hand-edited state
 * is no longer any preset — so the UI keeps it as a display hint and drops it
 * as soon as a manual edit happens.
 */

import { useCallback, useEffect, useState } from 'react'

import {
  api,
  ApiError,
  type Meta,
  type Scenario,
  type StateChange,
  type StateDocument,
} from '@/lib/api'

export interface StateResource {
  state: StateDocument | null
  meta: Meta | null
  scenarios: Scenario[]
  /** Scenario name that produced the current state, or null after a manual edit. */
  activeScenario: string | null
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  patch: (body: unknown) => Promise<StateDocument>
  reset: () => Promise<StateChange>
  applyScenario: (name: string) => Promise<StateChange>
  forget: () => void
}

export function useServerState(enabled: boolean): StateResource {
  const [state, setState] = useState<StateDocument | null>(null)
  const [meta, setMeta] = useState<Meta | null>(null)
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [activeScenario, setActiveScenario] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [document, catalogue, metaDocument] = await Promise.all([
        api.state(),
        api.scenarios(),
        api.meta(),
      ])
      setState(document)
      setScenarios(catalogue.scenarios)
      setMeta(metaDocument)
    } catch (cause) {
      if (cause instanceof ApiError && cause.isUnauthorized) {
        // Connection component owns the 401 flow; keep the view empty.
        setState(null)
        return
      }
      setError(cause instanceof ApiError ? cause.humanMessage : '读取状态失败')
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
    // A manual edit means the state is no longer any preset.
    setActiveScenario(null)
    return updated
  }, [])

  const reset = useCallback(async () => {
    const change = await api.reset()
    setState(change.after)
    setActiveScenario(null)
    return change
  }, [])

  const applyScenario = useCallback(async (name: string) => {
    const change = await api.applyScenario(name)
    setState(change.after)
    setActiveScenario(name)
    return change
  }, [])

  const forget = useCallback(() => {
    setState(null)
    setMeta(null)
    setScenarios([])
    setActiveScenario(null)
  }, [])

  return {
    state,
    meta,
    scenarios,
    activeScenario,
    loading,
    error,
    refresh,
    patch,
    reset,
    applyScenario,
    forget,
  }
}
