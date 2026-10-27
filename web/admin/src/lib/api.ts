/**
 * Typed client for the admin API.
 *
 * The token lives only in this module's memory (never localStorage, never the
 * URL). `ApiError` carries the server's structured field errors so forms can
 * render them without re-parsing messages.
 */

export type Amount = string

export interface Attachment {
  id: string
  name: string
  src: string
  kind: 'pdf' | 'doc' | 'xls' | 'zip'
  size_text: string
}

export interface Notice {
  id: string
  title: string
  department: string
  doc_no: string
  category: string
  current_fee: Amount
  previous_fee: Amount
  currency: string
  /** Single source of truth for the three rendered dates. */
  published_at: string
  effective_date: string
  /** Filled by the page script, like the portal's `_showDynClicks`. */
  view_count: number
  status: 'published' | 'withdrawn'
  body: string[]
  attachments: Attachment[]
  prev_title: string
  next_title: string
}

export interface BusinessData {
  notice: Notice
}

export interface StateDocument {
  revision: number
  business: BusinessData
}

export type ScenarioGroup = 'baseline' | 'fee' | 'content'

export interface Scenario {
  name: string
  description: string
  affects: string[]
  pages: string[]
  /** Human-facing Chinese title, authored on the server. */
  title: string
  /** One sentence describing what a collector will observe. */
  outcome: string
  /** Which business data a collector should see change. */
  data_impact: string
  group: ScenarioGroup
  compare_with_baseline: boolean
}

export type SelectorRole = 'primary' | 'ready' | 'supporting' | 'decoy'

export interface Selector {
  label: string
  css: string
  xpath: string
  role: SelectorRole
  note: string
}

export interface TargetPage {
  path: string
  purpose: string
  implemented: boolean
  collect_url: string
  preview_url: string
  selectors: Selector[]
}

export interface Meta {
  site_origin: string
  site_public_origin: string
  pages: TargetPage[]
}

export interface StateChange {
  before: StateDocument
  after: StateDocument
}

export interface FieldError {
  loc: string
  msg: string
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly errors: FieldError[]

  constructor(status: number, code: string, errors: FieldError[] = []) {
    super(code)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.errors = errors
  }

  get isUnauthorized(): boolean {
    return this.status === 401
  }

  /** Field errors keyed by dotted location, e.g. `business.notice.title`. */
  fieldErrors(): Map<string, string> {
    return new Map(this.errors.map((error) => [error.loc, error.msg]))
  }

  /** A message safe to show a user: never a raw status code alone. */
  get humanMessage(): string {
    switch (this.code) {
      case 'network_error':
        return '无法连接到管理服务，请确认服务仍在运行。'
      case 'unauthorized':
        return 'token 无效或已过期，请重新连接。'
      case 'invalid_state':
        return '提交的内容不符合校验规则，请检查标红的字段。'
      case 'unknown_scenario':
        return '该场景不存在，可能已被移除。'
      case 'body_too_large':
        return '请求体过大。'
      case 'unsupported_media_type':
        return '请求格式不被接受。'
      default:
        return `请求失败（${this.code}）。`
    }
  }
}

const BASE = ''

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH'
  body?: unknown
  signal?: AbortSignal
}

let token: string | null = null

export function setToken(value: string | null): void {
  token = value && value.trim() ? value.trim() : null
}

export function hasToken(): boolean {
  return token !== null
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'

  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
      cache: 'no-store',
    })
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw new ApiError(0, 'network_error')
  }

  if (response.status === 401) {
    // A stale token must not look like a generic failure: the UI drops back to
    // the connect screen instead of showing an empty state.
    token = null
    throw new ApiError(401, 'unauthorized')
  }

  const text = await response.text()
  const payload: unknown = text ? JSON.parse(text) : null

  if (!response.ok) {
    const body = (payload ?? {}) as { error?: string; errors?: FieldError[] }
    throw new ApiError(response.status, body.error ?? 'request_failed', body.errors ?? [])
  }

  return payload as T
}

export const api = {
  meta: (signal?: AbortSignal) => request<Meta>('/_admin/meta', { signal }),

  state: (signal?: AbortSignal) => request<StateDocument>('/_admin/state', { signal }),

  patchState: (body: unknown, signal?: AbortSignal) =>
    request<StateDocument>('/_admin/state', { method: 'PATCH', body, signal }),

  reset: () => request<StateChange>('/_admin/reset', { method: 'POST' }),

  scenarios: (signal?: AbortSignal) =>
    request<{ scenarios: Scenario[] }>('/_admin/scenarios', { signal }),

  applyScenario: (name: string) =>
    request<StateChange>(`/_admin/scenario/${encodeURIComponent(name)}`, { method: 'POST' }),
}
