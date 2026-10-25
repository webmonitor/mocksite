/**
 * Connection state: the token lives in `api.ts` memory only.
 *
 * Entering a token does not "log in" by itself — the first authenticated read
 * decides whether it works, so a wrong token is reported as a rejected
 * credential rather than a connected session.
 */

import { useCallback, useState } from 'react'

import { api, ApiError, hasToken, setToken } from '@/lib/api'

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error'

export interface Connection {
  status: ConnectionStatus
  message: string | null
  connect: (candidate: string) => Promise<boolean>
  disconnect: () => void
}

export function useConnection(): Connection {
  const [status, setStatus] = useState<ConnectionStatus>(hasToken() ? 'connected' : 'disconnected')
  const [message, setMessage] = useState<string | null>(null)

  const connect = useCallback(async (candidate: string): Promise<boolean> => {
    const trimmed = candidate.trim()
    if (!trimmed) {
      setStatus('error')
      setMessage('请输入管理 token')
      return false
    }

    setToken(trimmed)
    setStatus('connecting')
    setMessage(null)
    try {
      await api.state()
      setStatus('connected')
      setMessage(null)
      return true
    } catch (cause) {
      setToken(null)
      setStatus('error')
      if (cause instanceof ApiError && cause.status === 401) {
        setMessage('token 被拒绝（401）：请检查 MOCKSITE_TOKEN')
      } else if (cause instanceof ApiError && cause.status === 0) {
        setMessage('无法连接管理服务：请确认 9001 端口可达')
      } else {
        setMessage(cause instanceof Error ? cause.message : '连接失败')
      }
      return false
    }
  }, [])

  const disconnect = useCallback(() => {
    setToken(null)
    setStatus('disconnected')
    setMessage(null)
  }, [])

  return { status, message, connect, disconnect }
}
