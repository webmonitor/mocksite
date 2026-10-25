/**
 * Admin shell — a four-step workflow, not a wall of panels.
 *
 * The previous UI stacked five sections with no indication of what to do in
 * what order, and never showed the page being controlled. This one leads with
 * the loop a verification run actually follows:
 *
 *   ① 建立基线 → ② 应用变更 → ③ 核对页面 → ④ 恢复
 *
 * and keeps a live preview of the target page on screen the whole time, so
 * every mutation is immediately observable.
 */

import { useCallback, useMemo, useState } from 'react'

import { Explainer, Notice, Section, StepChip } from '@/components/ui'
import { useConnection } from '@/features/connection/useConnection'
import { PreviewPanel } from '@/features/preview/PreviewPanel'
import { FaultPanel } from '@/features/scenarios/FaultPanel'
import { ScenarioPicker } from '@/features/scenarios/ScenarioPicker'
import { BusinessEditor } from '@/features/state/BusinessEditor'
import { useServerState } from '@/features/state/useServerState'
import { SelectorReference, StateDiff } from '@/features/targets/SelectorReference'
import { ApiError, type StateChange } from '@/lib/api'

type Step = 1 | 2 | 3 | 4

export function AdminApp() {
  const connection = useConnection()
  const resource = useServerState(connection.status === 'connected')
  const [tokenInput, setTokenInput] = useState('')
  const [step, setStep] = useState<Step>(2)
  const [lastChange, setLastChange] = useState<StateChange | null>(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)

  const { state, meta, scenarios, activeScenario } = resource

  const activeScenarioTitle = useMemo(() => {
    if (!activeScenario) return null
    return scenarios.find((scenario) => scenario.name === activeScenario)?.title ?? activeScenario
  }, [activeScenario, scenarios])

  const runScenario = useCallback(
    async (name: string): Promise<StateChange> => {
      setBusy(true)
      setActionError(null)
      try {
        const change = await resource.applyScenario(name)
        setLastChange(change)
        setStep(3)
        return change
      } catch (cause) {
        const message = cause instanceof ApiError ? cause.humanMessage : '应用失败。'
        setActionError(message)
        throw cause
      } finally {
        setBusy(false)
      }
    },
    [resource],
  )

  const runReset = useCallback(async () => {
    setBusy(true)
    setActionError(null)
    try {
      const change = await resource.reset()
      setLastChange(change)
      setStep(1)
    } catch (cause) {
      setActionError(cause instanceof ApiError ? cause.humanMessage : '恢复失败。')
    } finally {
      setBusy(false)
    }
  }, [resource])

  const runPatch = useCallback(
    async (patch: unknown) => {
      setBusy(true)
      setActionError(null)
      try {
        await resource.patch(patch)
      } finally {
        setBusy(false)
      }
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
            先连接管理服务，再按左侧步骤走一遍验证流程。
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
          <span className="topbar-sub">可控 mock 目标站 · 验证采集与告警</span>
        </div>
        <div className="actions">
          <button type="button" onClick={() => void resource.refresh()} disabled={resource.loading}>
            {resource.loading ? '刷新中…' : '刷新状态'}
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
        <>
          <nav className="steps" aria-label="验证流程">
            <StepChip
              index={1}
              title="建立基线"
              detail={activeScenario === 'baseline' ? '已建立' : '恢复默认数据'}
              state={activeScenario === 'baseline' ? 'done' : step === 1 ? 'current' : 'todo'}
              onClick={() => setStep(1)}
            />
            <StepChip
              index={2}
              title="应用变更"
              detail={activeScenarioTitle ?? '选择场景或改数据'}
              state={step === 2 ? 'current' : 'todo'}
              onClick={() => setStep(2)}
            />
            <StepChip
              index={3}
              title="核对页面"
              detail="看右侧预览与提取结果"
              state={step === 3 ? 'current' : 'todo'}
              onClick={() => setStep(3)}
            />
            <StepChip
              index={4}
              title="恢复"
              detail="清除故障回到基线"
              state={step === 4 ? 'current' : 'todo'}
              onClick={() => setStep(4)}
            />
          </nav>

          <div className="workspace">
            <div className="workspace-main">
              {step === 1 ? (
                <Section
                  title="① 建立基线"
                  subtitle="每次验证都从已知状态开始，否则「变了」无从判断。"
                >
                  <div className="baseline-actions">
                    <button
                      type="button"
                      className="primary"
                      onClick={() => void runScenario('baseline')}
                      disabled={busy}
                    >
                      {busy ? '应用中…' : '应用基线场景'}
                    </button>
                    <button type="button" onClick={() => void runReset()} disabled={busy}>
                      恢复默认（reset）
                    </button>
                  </div>
                  <Explainer title="基线和 reset 有什么区别？">
                    <p>
                      两者都把数据恢复成默认值并清除故障。<code>baseline</code> 是一个场景，
                      会先构造完整目标状态再提交；<code>reset</code> 直接回到出厂默认状态。
                      验证脚本通常用 reset 建基线，因为它的语义最明确。
                    </p>
                  </Explainer>
                  <dl className="facts">
                    <dt>当前 revision</dt>
                    <dd>{state.revision}</dd>
                    <dt>商品现价</dt>
                    <dd>{state.business.product.current_price}</dd>
                    <dt>列表行</dt>
                    <dd>{state.business.items.map((item) => item.id).join(' / ') || '（空）'}</dd>
                    <dt>评价条数</dt>
                    <dd>{state.business.reviews.length}</dd>
                    <dt>故障</dt>
                    <dd>
                      {state.faults.kind === 'none' ? '无' : state.faults.kind}
                      {state.faults.delay_ms > 0 ? ` + ${state.faults.delay_ms}ms` : ''}
                    </dd>
                  </dl>
                </Section>
              ) : null}

              {step === 2 ? (
                <>
                  <Section
                    title="② 应用变更"
                    subtitle="选一个场景，或直接改数据。场景是绝对覆盖：每次应用都会从默认数据重建，不叠加。"
                  >
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
                    <BusinessEditor
                      business={state.business}
                      onSave={runPatch}
                      onDirtyChange={setDirty}
                    />
                  </Section>

                  <Section
                    title="故障注入"
                    subtitle="只影响站点端口，管理后台与 /health 始终可用。"
                  >
                    <FaultPanel faults={state.faults} onSave={runPatch} />
                  </Section>
                </>
              ) : null}

              {step === 3 ? (
                <>
                  <Section title="③ 核对页面" subtitle="右侧预览就是采集方实际取到的页面。">
                    <p className="hint">
                      确认三件事：页面上的内容是否符合预期、你用的选择器是否选中了正确的节点、
                      页面版本（revision）是否与预期一致。
                    </p>
                    <dl className="facts">
                      <dt>当前 revision</dt>
                      <dd>{state.revision}</dd>
                      <dt>生效场景</dt>
                      <dd>{activeScenarioTitle ?? '手动编辑的状态'}</dd>
                      <dt>未保存的编辑</dt>
                      <dd>{dirty ? '有（尚未生效）' : '无'}</dd>
                    </dl>
                    <Explainer title="为什么预览里的评价区一开始是骨架屏？">
                      <p>
                        评价是浏览器端渲染的：静态 HTML 里只有骨架屏，
                        <code>#reviews[data-ready="true"]</code> 要等第一页评价真正渲染后才会出现。
                        用 HTTP 抓取时拿不到评价，必须等 JS 执行完成——这正是要验证的差异。
                      </p>
                    </Explainer>
                  </Section>

                  {meta ? (
                    <Section
                      title="选择器参考"
                      subtitle="按用途分组。诱饵节点同样能被选中，但取到的不是你要的值。"
                    >
                      <SelectorReference pages={meta.pages} />
                    </Section>
                  ) : null}

                  {lastChange ? (
                    <Section title="本次变更" subtitle="服务端返回的前后状态对比。">
                      <StateDiff before={lastChange.before} after={lastChange.after} />
                    </Section>
                  ) : null}
                </>
              ) : null}

              {step === 4 ? (
                <Section title="④ 恢复" subtitle="故障不会自动恢复——这是刻意的，避免时序不确定。">
                  <div className="baseline-actions">
                    <button
                      type="button"
                      className="primary"
                      onClick={() => void runScenario('baseline')}
                      disabled={busy}
                    >
                      {busy ? '恢复中…' : '恢复到基线'}
                    </button>
                    <button type="button" onClick={() => void runReset()} disabled={busy}>
                      恢复默认（reset）
                    </button>
                  </div>
                  <p className="hint">
                    验证脚本观察到失败后，应显式调用恢复，再采集一次确认平台能回到正常状态。
                  </p>
                  <dl className="facts">
                    <dt>当前故障</dt>
                    <dd>{state.faults.kind === 'none' ? '无' : state.faults.kind}</dd>
                    <dt>当前延迟</dt>
                    <dd>{state.faults.delay_ms} ms</dd>
                  </dl>
                </Section>
              ) : null}
            </div>

            <aside className="workspace-side">
              {meta ? (
                <PreviewPanel
                  pages={meta.pages}
                  revision={state.revision}
                  activeScenarioTitle={activeScenarioTitle}
                />
              ) : null}
            </aside>
          </div>
        </>
      ) : (
        <Notice kind="info">读取状态中…</Notice>
      )}
    </main>
  )
}
