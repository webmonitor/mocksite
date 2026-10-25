/**
 * Fault injection controls.
 *
 * Faults are a real feature of the site port: they make the target fail or
 * respond slowly so a collector's error and timeout paths can be verified.
 * They never touch the admin port, `/health` or local assets — the port split
 * is the security boundary, so the copy says that out loud.
 *
 * Each control is one enum (never two booleans), and every option is explained
 * in terms of what a *collector* will see.
 */

import { useState } from 'react'

import { Notice } from '@/components/ui'
import { ApiError, type Faults } from '@/lib/api'

const FAULT_OPTIONS: { value: Faults['kind']; label: string; help: string }[] = [
  { value: 'none', label: '正常响应', help: '页面与 /api/data 正常返回' },
  { value: 'outage', label: '500 故障', help: '业务路由全部 500；后台与 /health 不受影响' },
]

export function FaultPanel({
  faults,
  onSave,
}: {
  faults: Faults
  onSave: (patch: unknown) => Promise<void>
}) {
  const [kind, setKind] = useState<Faults['kind']>(faults.kind)
  const [delay, setDelay] = useState(String(faults.delay_ms))
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)

  const submit = async () => {
    setSaving(true)
    setMessage(null)
    const delayMs = Number(delay)
    try {
      // The server validates the range; an unparsable value is sent through so
      // it comes back as a field error instead of being silently coerced.
      await onSave({ faults: { kind, delay_ms: Number.isFinite(delayMs) ? delayMs : delay } })
      setMessage({ kind: 'ok', text: '故障设置已更新，右侧预览已刷新。' })
    } catch (cause) {
      setMessage({
        kind: 'error',
        text: cause instanceof ApiError ? cause.humanMessage : '更新失败。',
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fault-panel">
      <p className="hint">
        故障只影响站点端口（<code>:9000</code>），管理后台与 <code>/health</code> 始终可用，
        因此即使站点在返回 500，也能从这里恢复。故障不会自动恢复，需要显式应用基线或 reset。
      </p>

      <div className="option-groups">
        <fieldset className="option-group">
          <legend>
            故障注入 <code>只影响站点端口</code>
          </legend>
          {FAULT_OPTIONS.map((option) => (
            <label
              key={option.value}
              className={`option${kind === option.value ? ' option-active' : ''}`}
            >
              <input
                type="radio"
                name="fault-kind"
                value={option.value}
                checked={kind === option.value}
                onChange={() => setKind(option.value)}
              />
              <span>
                <strong>{option.label}</strong>
                <small>{option.help}</small>
              </span>
            </label>
          ))}
          <label className="delay-field">
            <span>额外延迟（毫秒，0–30000）</span>
            <input
              id="fault-delay"
              inputMode="numeric"
              value={delay}
              onChange={(e) => setDelay(e.target.value)}
            />
            <small>500 故障优先于延迟：两者同时设置时返回 500。</small>
          </label>
        </fieldset>
      </div>

      <div className="actions">
        <button type="button" className="primary" onClick={() => void submit()} disabled={saving}>
          {saving ? '提交中…' : '应用故障设置'}
        </button>
        <button
          type="button"
          onClick={() => {
            setKind(faults.kind)
            setDelay(String(faults.delay_ms))
          }}
          disabled={saving}
        >
          重置为已生效值
        </button>
      </div>

      {message ? <Notice kind={message.kind}>{message.text}</Notice> : null}
    </div>
  )
}
