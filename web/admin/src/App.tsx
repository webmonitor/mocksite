/** Admin shell: connection gate, state overview, editor, scenarios, pages. */

import { useState } from 'react'

import { Field, Notice, Section } from '@/components/ui'
import { useConnection } from '@/features/connection/useConnection'
import { ScenarioPanel, PresentationPanel } from '@/features/scenarios/ScenarioPanel'
import { BusinessEditor } from '@/features/state/BusinessEditor'
import { useServerState } from '@/features/state/useServerState'
import { TargetPanel } from '@/features/targets/TargetPanel'

export function AdminApp() {
  const connection = useConnection()
  const resource = useServerState(connection.status === 'connected')
  const [tokenInput, setTokenInput] = useState('')

  if (connection.status !== 'connected') {
    return (
      <main className="shell shell-narrow">
        <h1>mocksite 管理后台</h1>
        <Section title="连接">
          <form
            onSubmit={(event) => {
              event.preventDefault()
              void connection.connect(tokenInput).then((ok) => {
                // The state hook re-fetches once the status flips to connected.
                if (ok) setTokenInput('')
              })
            }}
          >
            <Field
              label="管理 token"
              htmlFor="token"
              hint="来自 MOCKSITE_TOKEN；只保存在本页内存中，刷新或退出后清除"
            >
              <input
                id="token"
                type="password"
                autoComplete="off"
                value={tokenInput}
                onChange={(event) => setTokenInput(event.target.value)}
                disabled={connection.status === 'connecting'}
              />
            </Field>
            <div className="actions">
              <button type="submit" className="primary" disabled={connection.status === 'connecting'}>
                {connection.status === 'connecting' ? '连接中…' : '连接'}
              </button>
            </div>
          </form>
          {connection.message ? <Notice kind="error">{connection.message}</Notice> : null}
        </Section>
      </main>
    )
  }

  const { state, meta, scenarios } = resource

  return (
    <main className="shell">
      <header className="topbar">
        <h1>mocksite 管理后台</h1>
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

      {state ? (
        <>
          <Section
            title="状态总览"
            actions={
              <span className="badge" data-testid="revision">
                revision {state.revision}
              </span>
            }
          >
            <div className="grid">
              <div>
                <h3>商品</h3>
                <dl className="facts">
                  <dt>ID</dt>
                  <dd>{state.business.product.id}</dd>
                  <dt>名称</dt>
                  <dd>{state.business.product.name}</dd>
                  <dt>现价</dt>
                  <dd>{state.business.product.current_price}</dd>
                  <dt>原价</dt>
                  <dd>{state.business.product.original_price}</dd>
                  <dt>币种</dt>
                  <dd>{state.business.product.currency}</dd>
                </dl>
              </div>
              <div>
                <h3>列表</h3>
                <dl className="facts">
                  <dt>行数</dt>
                  <dd>{state.business.items.length}</dd>
                  <dt>页大小</dt>
                  <dd>{state.business.page_size}</dd>
                  <dt>行 ID</dt>
                  <dd>{state.business.items.map((item) => item.id).join(' → ') || '（空）'}</dd>
                </dl>
              </div>
              <div>
                <h3>控制项</h3>
                <dl className="facts">
                  <dt>商品现价呈现</dt>
                  <dd>{state.presentation.product_price}</dd>
                  <dt>行价格呈现</dt>
                  <dd>{state.presentation.item_price}</dd>
                  <dt>故障</dt>
                  <dd>
                    {state.faults.kind}
                    {state.faults.delay_ms > 0 ? ` + ${state.faults.delay_ms}ms` : ''}
                  </dd>
                </dl>
              </div>
            </div>
          </Section>

          <Section title="数据编辑">
            <BusinessEditor
              business={state.business}
              onSave={async (patch) => {
                await resource.patch(patch)
              }}
            />
          </Section>

          <PresentationPanel
            presentation={state.presentation}
            faults={state.faults}
            onSave={async (patch) => {
              await resource.patch(patch)
            }}
          />

          <ScenarioPanel
            scenarios={scenarios}
            revision={state.revision}
            onApply={(name) => resource.applyScenario(name)}
            onReset={() => resource.reset()}
          />

          {meta ? <TargetPanel pages={meta.pages} /> : null}
        </>
      ) : (
        <Notice kind="info">读取状态中…</Notice>
      )}
    </main>
  )
}
