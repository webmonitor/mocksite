/**
 * Scenario and fault controls.
 *
 * Applying a preset or resetting replaces the whole state, so both actions ask
 * for confirmation first and then report the before/after revisions. The
 * affected-scope text comes from the server, never from a local copy.
 */

import { useState } from 'react'

import { Notice, Section } from '@/components/ui'
import { ApiError, type Faults, type Presentation, type Scenario, type StateChange } from '@/lib/api'

export function ScenarioPanel({
  scenarios,
  onApply,
  onReset,
  revision,
}: {
  scenarios: Scenario[]
  onApply: (name: string) => Promise<StateChange>
  onReset: () => Promise<StateChange>
  revision: number
}) {
  const [busy, setBusy] = useState<string | null>(null)
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [pending, setPending] = useState<{ kind: 'scenario'; name: string } | { kind: 'reset' } | null>(null)

  const run = async (action: { kind: 'scenario'; name: string } | { kind: 'reset' }) => {
    setBusy(action.kind === 'reset' ? 'reset' : action.name)
    setMessage(null)
    try {
      const change = action.kind === 'reset' ? await onReset() : await onApply(action.name)
      const label = action.kind === 'reset' ? '已恢复默认' : `已应用 ${action.name}`
      setMessage({
        kind: 'ok',
        text: `${label}：revision ${change.before.revision} → ${change.after.revision}`,
      })
    } catch (cause) {
      const detail = cause instanceof ApiError ? `（${cause.code}）` : ''
      setMessage({ kind: 'error', text: `操作失败${detail}，状态未改变` })
    } finally {
      setBusy(null)
      setPending(null)
    }
  }

  return (
    <Section
      title="场景与故障"
      actions={
        <button type="button" onClick={() => setPending({ kind: 'reset' })} disabled={busy !== null}>
          恢复默认
        </button>
      }
    >
      <p className="hint">
        当前 revision：<strong>{revision}</strong>。每个场景从默认数据构造完整目标状态，应用后覆盖当前状态。
      </p>

      <ul className="scenarios">
        {scenarios.map((scenario) => (
          <li key={scenario.name}>
            <div className="scenario-head">
              <code>{scenario.name}</code>
              <button
                type="button"
                onClick={() => setPending({ kind: 'scenario', name: scenario.name })}
                disabled={busy !== null}
              >
                {busy === scenario.name ? '应用中…' : '应用'}
              </button>
            </div>
            <p>{scenario.description}</p>
            <p className="hint">影响：{scenario.affects.join('、')}</p>
            <p className="hint">页面：{scenario.pages.join('、')}</p>
          </li>
        ))}
      </ul>

      {pending ? (
        <div className="confirm" role="alertdialog" aria-label="确认覆盖当前状态">
          <p>
            将覆盖当前状态并推进 revision（{pending.kind === 'reset' ? '恢复默认' : `应用 ${pending.name}`}）。
            继续？
          </p>
          <div className="actions">
            <button type="button" className="primary" onClick={() => void run(pending)} disabled={busy !== null}>
              确认
            </button>
            <button type="button" onClick={() => setPending(null)} disabled={busy !== null}>
              取消
            </button>
          </div>
        </div>
      ) : null}

      {message ? <Notice kind={message.kind}>{message.text}</Notice> : null}
    </Section>
  )
}

export function PresentationPanel({
  presentation,
  faults,
  onSave,
}: {
  presentation: Presentation
  faults: Faults
  onSave: (patch: unknown) => Promise<void>
}) {
  const [productPrice, setProductPrice] = useState(presentation.product_price)
  const [itemPrice, setItemPrice] = useState(presentation.item_price)
  const [kind, setKind] = useState(faults.kind)
  const [delay, setDelay] = useState(String(faults.delay_ms))
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)

  const submit = async () => {
    setSaving(true)
    setMessage(null)
    const delayMs = Number(delay)
    try {
      await onSave({
        presentation: { product_price: productPrice, item_price: itemPrice },
        faults: { kind, delay_ms: Number.isFinite(delayMs) ? delayMs : delay },
      })
      setMessage({ kind: 'ok', text: '控制项已更新' })
    } catch (cause) {
      const detail = cause instanceof ApiError ? `（${cause.code}）` : ''
      setMessage({ kind: 'error', text: `更新失败${detail}` })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Section title="呈现与故障控制项">
      <div className="grid">
        <label className="field" htmlFor="presentation-product-price">
          <span>商品现价呈现</span>
          <select
            id="presentation-product-price"
            value={productPrice}
            onChange={(e) => setProductPrice(e.target.value as Presentation['product_price'])}
          >
            <option value="normal">normal（正常）</option>
            <option value="empty">empty（节点保留，文本为空）</option>
            <option value="missing">missing（移除节点）</option>
            <option value="renamed">renamed（改 ID 保留文本）</option>
          </select>
        </label>
        <label className="field" htmlFor="presentation-item-price">
          <span>行价格呈现</span>
          <select
            id="presentation-item-price"
            value={itemPrice}
            onChange={(e) => setItemPrice(e.target.value as Presentation['item_price'])}
          >
            <option value="normal">normal（td.price）</option>
            <option value="renamed">renamed（td.cost）</option>
          </select>
        </label>
        <label className="field" htmlFor="fault-kind">
          <span>故障类型</span>
          <select id="fault-kind" value={kind} onChange={(e) => setKind(e.target.value as Faults['kind'])}>
            <option value="none">none（正常响应）</option>
            <option value="outage">outage（业务路由 500）</option>
          </select>
        </label>
        <label className="field" htmlFor="fault-delay">
          <span>延迟（毫秒，0–30000）</span>
          <input id="fault-delay" inputMode="numeric" value={delay} onChange={(e) => setDelay(e.target.value)} />
        </label>
      </div>
      <p className="hint">故障只影响站点业务路由；管理后台与 /health 始终可用。</p>
      <div className="actions">
        <button type="button" className="primary" onClick={() => void submit()} disabled={saving}>
          {saving ? '提交中…' : '应用控制项'}
        </button>
      </div>
      {message ? <Notice kind={message.kind}>{message.text}</Notice> : null}
    </Section>
  )
}
