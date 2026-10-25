/**
 * Target page directory.
 *
 * Two URLs per page on purpose: the collect URL is what a monitoring platform
 * resolves (container DNS), the preview URL is what a developer's browser can
 * open. Conflating them is a classic source of "works in the admin, 404 in the
 * worker" bugs, so the UI never shows just one.
 */

import { CopyButton, Notice, Section } from '@/components/ui'
import type { TargetPage } from '@/lib/api'

export function TargetPanel({ pages }: { pages: TargetPage[] }) {
  return (
    <Section title="目标页面">
      <p className="hint">采集地址用于监控平台；预览地址用于本机浏览器。两者不可互换。</p>
      <ul className="pages">
        {pages.map((page) => (
          <li key={page.path}>
            <div className="page-head">
              <code>{page.path}</code>
              {page.implemented ? <span className="badge">已实现</span> : <span className="badge badge-planned">规划中</span>}
              <a href={page.preview_url} target="_blank" rel="noreferrer">
                新标签页打开
              </a>
            </div>
            <p>{page.purpose}</p>
            <dl className="urls">
              <dt>采集地址</dt>
              <dd>
                <code>{page.collect_url}</code> <CopyButton value={page.collect_url} />
              </dd>
              <dt>预览地址</dt>
              <dd>
                <code>{page.preview_url}</code> <CopyButton value={page.preview_url} />
              </dd>
            </dl>
            {page.selectors.length > 0 ? (
              <table className="selectors">
                <thead>
                  <tr>
                    <th>目标</th>
                    <th>CSS</th>
                    <th>XPath</th>
                  </tr>
                </thead>
                <tbody>
                  {page.selectors.map((selector) => (
                    <tr key={selector.label}>
                      <td>{selector.label}</td>
                      <td>
                        <code>{selector.css}</code> <CopyButton value={selector.css} label="复制 CSS" />
                      </td>
                      <td>
                        <code>{selector.xpath}</code> <CopyButton value={selector.xpath} label="复制 XPath" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <Notice kind="info">该路径返回 JSON 或纯文本，无需选择器。</Notice>
            )}
          </li>
        ))}
      </ul>
    </Section>
  )
}
