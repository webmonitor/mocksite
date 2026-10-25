/**
 * Typed client for the admin API.
 *
 * The token lives only in this module's memory (never localStorage, never the
 * URL). `ApiError` carries the server's structured field errors so forms can
 * render them without re-parsing messages.
 */

export type Price = string

export interface Product {
  id: string
  name: string
  current_price: Price
  original_price: Price
  currency: string
}

export interface Item {
  id: string
  name: string
  price: Price
}

export interface BusinessData {
  product: Product
  items: Item[]
  page_size: number
}

export type ProductPriceRendering = 'normal' | 'empty' | 'missing' | 'renamed'
export type ItemPriceRendering = 'normal' | 'renamed'
export type FaultKind = 'none' | 'outage'

export interface Presentation {
  product_price: ProductPriceRendering
  item_price: ItemPriceRendering
}

export interface Faults {
  kind: FaultKind
  delay_ms: number
}

export interface StateDocument {
  revision: number
  business: BusinessData
  presentation: Presentation
  faults: Faults
}

export interface Scenario {
  name: string
  description: string
  affects: string[]
  pages: string[]
}

export interface Selector {
  label: string
  css: string
  xpath: string
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

  /** Field errors keyed by dotted location, e.g. `business.product.name`. */
  fieldErrors(): Map<string, string> {
    return new Map(this.errors.map((error) => [error.loc, error.msg]))
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

  scenarios: (signal?: AbortSignal) => request<{ scenarios: Scenario[] }>('/_admin/scenarios', { signal }),

  applyScenario: (name: string) =>
    request<StateChange>(`/_admin/scenario/${encodeURIComponent(name)}`, { method: 'POST' }),
}
