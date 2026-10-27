/**
 * Scenario picker.
 *
 * Each card shows a Chinese title, what a collector will observe, and which
 * data field changes. The copy comes from the server, so the UI and the API can
 * never disagree.
 */

import { useMemo, useState } from 'react'

import { Notice } from '@/components/ui'
import { ApiError, type Scenario, type ScenarioGroup, type StateChange } from '@/lib/api'

const GROUPS: { key: ScenarioGroup; label: string; hint: string }[] = [
  { key: 'baseline', label: '基线', hint: '建立或恢复已知起点' },
  { key: 'fee', label: '收费标准', hint: '通知现行标准' },
  { key: 'content', label: '通知内容', hint: '状态、执行日期、标题、点击次数' },
]

export function ScenarioPicker({
  scenarios,
  activeScenario,
  busy,
  onApply,
}: {
  scenarios: Scenario[]
  activeScenario: string | null
  busy: boolean
  onApply: (name: string) => Promise<StateChange>
}) {
  const [group, setGroup] = useState<ScenarioGroup>('fee')
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [pending, setPending] = useState<string | null>(null)

  const visible = useMemo(
    () => scenarios.filter((scenario) => scenario.group === group),
    [scenarios, group],
  )

  const run = async (name: string) => {
    setMessage(null)
    try {
      const change = await onApply(name)
      setMessage({
        kind: 'ok',
        text: `已应用，revision ${change.before.revision} → ${change.after.revision}。右侧预览已刷新。`,
      })
    } catch (cause) {
      setMessage({
        kind: 'error',
        text: cause instanceof ApiError ? cause.humanMessage : '应用失败，状态未改变。',
      })
    } finally {
      setPending(null)
    }
  }

  return (
    <div className="scenario-picker">
      <div className="group-tabs" role="tablist" aria-label="场景分组">
        {GROUPS.map((entry) => {
          const count = scenarios.filter((scenario) => scenario.group === entry.key).length
          return (
            <button
              key={entry.key}
              type="button"
              role="tab"
              aria-selected={group === entry.key}
              className={group === entry.key ? 'group-tab group-tab-active' : 'group-tab'}
              onClick={() => setGroup(entry.key)}
            >
              <strong>{entry.label}</strong>
              <small>
                {entry.hint} · {count}
              </small>
            </button>
          )
        })}
      </div>

      <ul className="scenario-cards">
        {visible.map((scenario) => {
          const isActive = scenario.name === activeScenario
          return (
            <li
              key={scenario.name}
              className={`scenario-card${isActive ? ' scenario-card-active' : ''}`}
            >
              <div className="scenario-card-head">
                <h3>{scenario.title || scenario.name}</h3>
                {isActive ? <span className="badge badge-live">当前生效</span> : null}
              </div>

              <p className="scenario-outcome">{scenario.outcome || scenario.description}</p>

              {scenario.data_impact ? (
                <p className="scenario-impact">
                  <span className="impact-label">数据变化</span>
                  {scenario.data_impact}
                </p>
              ) : null}

              <div className="scenario-card-foot">
                <code className="scenario-code" title="场景标识，用于 API 调用">
                  {scenario.name}
                </code>
                {pending === scenario.name ? (
                  <div className="confirm-inline">
                    <span>将覆盖当前状态，继续？</span>
                    <button
                      type="button"
                      className="primary"
                      onClick={() => void run(scenario.name)}
                      disabled={busy}
                    >
                      确认
                    </button>
                    <button type="button" onClick={() => setPending(null)} disabled={busy}>
                      取消
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    className="primary"
                    onClick={() => setPending(scenario.name)}
                    disabled={busy || isActive}
                  >
                    {isActive ? '已生效' : '应用此场景'}
                  </button>
                )}
              </div>
            </li>
          )
        })}
      </ul>

      {message ? <Notice kind={message.kind}>{message.text}</Notice> : null}
    </div>
  )
}
