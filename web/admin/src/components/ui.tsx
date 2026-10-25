/** Minimal shared UI primitives; no component library, no CDN. */

import type { ReactNode } from 'react'

export function Section({ title, children, actions }: { title: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="section">
      <header className="section-head">
        <h2>{title}</h2>
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
      className="link"
      onClick={() => {
        void navigator.clipboard?.writeText(value)
      }}
      title={value}
    >
      {label}
    </button>
  )
}
