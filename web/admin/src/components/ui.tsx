/** Minimal shared UI primitives; no component library, no CDN. */

import type { ReactNode } from 'react'

export function Section({
  title,
  subtitle,
  children,
  actions,
  id,
}: {
  title: string
  subtitle?: string
  children: ReactNode
  actions?: ReactNode
  id?: string
}) {
  return (
    <section className="section" id={id}>
      <header className="section-head">
        <div>
          <h2>{title}</h2>
          {subtitle ? <p className="section-sub">{subtitle}</p> : null}
        </div>
        {actions}
      </header>
      {children}
    </section>
  )
}

export function Field({
  label,
  htmlFor,
  error,
  hint,
  children,
}: {
  label: string
  htmlFor: string
  error?: string
  hint?: string
  children: ReactNode
}) {
  return (
    <div className={`field${error ? ' field-invalid' : ''}`}>
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && !error ? <p className="hint">{hint}</p> : null}
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  )
}

export function Notice({ kind, children }: { kind: 'ok' | 'warn' | 'error' | 'info'; children: ReactNode }) {
  return (
    <p className={`notice notice-${kind}`} role={kind === 'error' ? 'alert' : 'status'}>
      {children}
    </p>
  )
}

export function CopyButton({ value, label = '复制' }: { value: string; label?: string }) {
  return (
    <button
      type="button"
      className="copy"
      onClick={() => {
        void navigator.clipboard?.writeText(value)
      }}
      title={value}
    >
      {label}
    </button>
  )
}

/** A step in the top workflow bar. */
export function StepChip({
  index,
  title,
  detail,
  state,
  onClick,
}: {
  index: number
  title: string
  detail: string
  state: 'done' | 'current' | 'todo'
  onClick: () => void
}) {
  return (
    <button type="button" className={`step step-${state}`} onClick={onClick}>
      <span className="step-index">{state === 'done' ? '✓' : index}</span>
      <span className="step-text">
        <strong>{title}</strong>
        <small>{detail}</small>
      </span>
    </button>
  )
}

/** A collapsible explanation panel — the "why" that a newcomer needs. */
export function Explainer({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="explainer">
      <summary>{title}</summary>
      <div className="explainer-body">{children}</div>
    </details>
  )
}
