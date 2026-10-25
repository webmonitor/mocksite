/**
 * Selector reference and state diff.
 *
 * Two things the old UI made hard:
 *
 * 1. Which selector is the one to monitor, and which are decoys. The server
 *    tags every selector with a role, so the page can group them instead of
 *    dumping a flat list.
 * 2. What actually changed after a mutation. The server returns before/after
 *    states; this renders a field-level diff instead of a bare revision bump.
 */

import { CopyButton } from '@/components/ui'
import type { Selector, StateDocument, TargetPage } from '@/lib/api'

const ROLE_LABELS: Record<string, { title: string; hint: string; tone: string }> = {
  primary: { title: '主要目标', hint: '通常应当监控的节点', tone: 'role-primary' },
  ready: { title: '就绪标记', hint: '等待渲染完成的判据', tone: 'role-ready' },
  supporting: { title: '辅助字段', hint: '可选监控的补充信息', tone: 'role-supporting' },
  decoy: { title: '诱饵节点', hint: '形状相似但语义不同，误选会得到错误数据', tone: 'role-decoy' },
}

const ROLE_ORDER = ['primary', 'ready', 'supporting', 'decoy']

export function SelectorReference({ pages }: { pages: TargetPage[] }) {
  return (
    <div className="selector-reference">
      {pages
        .filter((page) => page.implemented && page.selectors.length > 0)
        .map((page) => (
          <article key={page.path} className="selector-page">
            <header>
              <h3>
                <code>{page.path}</code>
              </h3>
              <p className="hint">{page.purpose}</p>
            </header>

            {ROLE_ORDER.map((role) => {
              const selectors = page.selectors.filter((selector) => selector.role === role)
              if (selectors.length === 0) return null
              const meta = ROLE_LABELS[role] ?? {
                title: role,
                hint: '',
                tone: 'role-supporting',
              }
              return (
                <section key={role} className={`role-block ${meta.tone}`}>
                  <h4>
                    {meta.title}
                    <small>{meta.hint}</small>
                  </h4>
                  <ul>
                    {selectors.map((selector) => (
                      <SelectorRow key={`${selector.css}-${selector.label}`} selector={selector} />
                    ))}
                  </ul>
                </section>
              )
            })}
          </article>
        ))}
    </div>
  )
}

function SelectorRow({ selector }: { selector: Selector }) {
  return (
    <li className="selector-row">
      <div className="selector-head">
        <strong>{selector.label}</strong>
        {selector.note ? <span className="selector-note">{selector.note}</span> : null}
      </div>
      <div className="selector-code">
        <span className="code-label">CSS</span>
        <code>{selector.css}</code>
        <CopyButton value={selector.css} />
      </div>
      <div className="selector-code">
        <span className="code-label">XPath</span>
        <code>{selector.xpath}</code>
        <CopyButton value={selector.xpath} />
      </div>
    </li>
  )
}

interface Difference {
  path: string
  before: string
  after: string
}

function flatten(value: unknown, prefix: string, out: Map<string, string>): void {
  if (Array.isArray(value)) {
    out.set(prefix, `${value.length} 项`)
    value.forEach((entry, index) => flatten(entry, `${prefix}[${index}]`, out))
    return
  }
  if (value && typeof value === 'object') {
    for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
      flatten(child, prefix ? `${prefix}.${key}` : key, out)
    }
    return
  }
  out.set(prefix, String(value))
}

export function diffStates(before: StateDocument, after: StateDocument): Difference[] {
  const left = new Map<string, string>()
  const right = new Map<string, string>()
  flatten(before, '', left)
  flatten(after, '', right)

  const keys = new Set([...left.keys(), ...right.keys()])
  const differences: Difference[] = []
  for (const key of [...keys].sort()) {
    const a = left.get(key) ?? '（无）'
    const b = right.get(key) ?? '（无）'
    if (a !== b) differences.push({ path: key, before: a, after: b })
  }
  return differences
}

export function StateDiff({ before, after }: { before: StateDocument; after: StateDocument }) {
  const differences = diffStates(before, after)
  if (differences.length === 0) {
    return <p className="hint">内容完全相同，只有 revision 变化——这正是 no_change 场景要验证的。</p>
  }
  return (
    <table className="diff-table">
      <thead>
        <tr>
          <th>字段</th>
          <th>之前</th>
          <th>之后</th>
        </tr>
      </thead>
      <tbody>
        {differences.slice(0, 40).map((difference) => (
          <tr key={difference.path}>
            <td>
              <code>{difference.path}</code>
            </td>
            <td className="diff-before">{difference.before}</td>
            <td className="diff-after">{difference.after}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
