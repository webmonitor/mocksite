/**
 * Admin shell — a single page, not a wizard.
 *
 * Everything a verification run needs is on one screen, because the loop is
 * short: apply a scenario (or edit the notice), watch the page change, restore.
 * The live preview sits beside the controls so a change and its effect are
 * always visible together.
 */

import { useCallback, useMemo, useState } from 'react'

import { Notice, Section } from '@/components/ui'
import { useConnection } from '@/features/connection/useConnection'
import { PreviewPanel } from '@/features/preview/PreviewPanel'
import { ScenarioPicker } from '@/features/scenarios/ScenarioPicker'
import { BusinessEditor } from '@/features/state/BusinessEditor'
import { useServerState } from '@/features/state/useServerState'
import { ApiError, type StateChange } from '@/lib/api'

export function AdminApp() {
  const connection = useConnection()
  const resource = useServerState(connection.status === 'connected')
  const [tokenInput, setTokenInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const { state, meta, scenarios, activeScenario } = resource

  const activeScenarioTitle = useMemo(() => {
    const scenario = scenarios.find((entry) => entry.name === activeScenario)
    return scenario?.title ?? null
  }, [activeScenario, scenarios])

  // Scenario failures are rendered by the picker (it knows which card failed),
  // so the rejection is propagated rather than duplicated at the page level.
  const runScenario = useCallback(
    async (name: string): Promise<StateChange> => resource.applyScenario(name),
    [resource],
  )

  const runReset = useCallback(async () => {
    setBusy(true)
    setActionError(null)
    try {
      await resource.reset()
    } catch (cause) {
      setActionError(cause instanceof ApiError ? cause.humanMessage : '恢复失败。')
    } finally {
      setBusy(false)
    }
  }, [resource])

  // Errors are the editor's to render: it owns the field-level messages and the
  // "draft preserved" behaviour, so this must not swallow the rejection.
  const runPatch = useCallback(
    async (patch: unknown) => {
      setActionError(null)
      await resource.patch(patch)
    },
    [resource],
  )

  if (connection.status !== 'connected') {
    return (
      <main className="shell shell-narrow">
        <div className="connect-card">
          <h1>mocksite 控制台</h1>
          <p className="lede">
            这是一个可控的 mock 目标站，用来验证采集系统「抓得对不对、变没变、坏了怎么办」。
            先连接管理服务，再改数据或应用场景。
          </p>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              void connection.connect(tokenInput).then((ok) => {
                // The state hook re-fetches once the status flips to connected.
                if (ok) setTokenInput('')
              })
            }}
          >
            <label htmlFor="token">管理 token</label>
            <input
              id="token"
              type="password"
              autoComplete="off"
              placeholder="MOCKSITE_TOKEN"
              value={tokenInput}
              onChange={(event) => setTokenInput(event.target.value)}
              disabled={connection.status === 'connecting'}
            />
            <p className="hint">
              token 来自 <code>MOCKSITE_TOKEN</code>，只保存在本页内存中，刷新或退出后即清除。
            </p>
            <button type="submit" className="primary" disabled={connection.status === 'connecting'}>
              {connection.status === 'connecting' ? '连接中…' : '连接'}
            </button>
          </form>
          {connection.message ? <Notice kind="error">{connection.message}</Notice> : null}
        </div>
      </main>
    )
  }

  return (
    <main className="shell shell-wide">
      <header className="topbar">
        <div className="topbar-title">
          <h1>mocksite 控制台</h1>
          <span className="topbar-sub">单条通知 · 可控数据 · 实时预览</span>
        </div>
        <div className="actions">
          <button type="button" onClick={() => void resource.refresh()} disabled={resource.loading}>
            {resource.loading ? '刷新中…' : '刷新状态'}
          </button>
          <button type="button" onClick={() => void runReset()} disabled={busy}>
            {busy ? '恢复中…' : '恢复默认（reset）'}
          </button>
          <button
            type="button"
            onClick={() => {
              resource.forget()
              connection.disconnect()
            }}
          >
            退出
          </button>
        </div>
      </header>

      {resource.error ? <Notice kind="error">{resource.error}</Notice> : null}
      {actionError ? <Notice kind="error">{actionError}</Notice> : null}

      {state ? (
        <div className="workspace">
          <div className="workspace-main">
            <Section title="场景" subtitle="场景是绝对覆盖：每次应用都从默认数据重建，不叠加。">
              <ScenarioPicker
                scenarios={scenarios}
                activeScenario={activeScenario}
                busy={busy}
                onApply={runScenario}
              />
            </Section>

            <Section
              title="手动编辑数据"
              subtitle="比场景更灵活；保存后当前状态就不再对应任何预设场景。"
            >
              <BusinessEditor business={state.business} onSave={runPatch} />
            </Section>
          </div>

          <aside className="workspace-side">
            {meta ? (
              <PreviewPanel
                pages={meta.pages}
                revision={state.revision}
                activeScenarioTitle={activeScenarioTitle}
              />
            ) : null}
            <dl className="facts">
              <dt>当前 revision</dt>
              <dd>{state.revision}</dd>
              <dt>生效场景</dt>
              <dd>{activeScenarioTitle ?? '手动编辑的状态'}</dd>
              <dt>现行标准</dt>
              <dd>{state.business.notice.current_fee}</dd>
              <dt>点击次数</dt>
              <dd>{state.business.notice.view_count}</dd>
            </dl>
          </aside>
        </div>
      ) : (
        <Notice kind="info">读取状态中…</Notice>
      )}
    </main>
  )
}
