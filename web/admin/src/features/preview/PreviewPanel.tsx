/**
 * Live preview of a target page, embedded in the admin UI.
 *
 * This is the feature that makes the workflow legible: after applying a
 * scenario or editing data you see the actual page the collector will fetch,
 * without leaving the admin. The iframe points at the *preview* origin (the
 * browser-reachable one), never the collect origin.
 */

import { useEffect, useLayoutEffect, useRef, useState } from 'react'

import { CopyButton } from '@/components/ui'
import type { TargetPage } from '@/lib/api'

/** Pages worth previewing first, in workflow order. */
const PREFERRED = ['/static/product', '/ssr/product', '/react/list', '/dynamic/deals', '/api/data']

/**
 * The preview renders the page at this width and scales it down to fit.
 *
 * Rendering the iframe at its container width was wrong: the product page has
 * a 900px breakpoint, so a narrow panel stacked the buy box *below* the gallery
 * and the price — the one thing the preview exists to show — was off-screen.
 */
const DESKTOP_WIDTH = 1180

function orderPages(pages: TargetPage[]): TargetPage[] {
  const rank = (page: TargetPage) => {
    const index = PREFERRED.indexOf(page.path)
    return index === -1 ? PREFERRED.length : index
  }
  return [...pages].sort((a, b) => rank(a) - rank(b))
}

export function PreviewPanel({
  pages,
  revision,
  activeScenarioTitle,
}: {
  pages: TargetPage[]
  revision: number
  activeScenarioTitle: string | null
}) {
  const ordered = orderPages(pages.filter((page) => page.implemented))
  const [path, setPath] = useState(ordered[0]?.path ?? '/static/product')
  // `nonce` forces a reload after every state change, so the preview can never
  // show a stale page while the revision badge claims otherwise.
  const [nonce, setNonce] = useState(0)
  const [scale, setScale] = useState(1)
  const [height, setHeight] = useState(720)
  const shell = useRef<HTMLDivElement>(null)
  const frame = useRef<HTMLIFrameElement>(null)

  useEffect(() => {
    setNonce((value) => value + 1)
  }, [revision, path])

  // Fit the fixed-width page into whatever room the panel actually has.
  useLayoutEffect(() => {
    const node = shell.current
    if (!node) return
    const measure = () => {
      const available = node.clientWidth
      if (available > 0) setScale(Math.min(1, available / DESKTOP_WIDTH))
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  const current = ordered.find((page) => page.path === path) ?? ordered[0]
  const src = current ? `${current.preview_url}?rev=${revision}&n=${nonce}` : ''

  return (
    <div className="preview">
      <div className="preview-bar">
        <div className="preview-tabs" role="tablist" aria-label="预览页面">
          {ordered.map((page) => (
            <button
              key={page.path}
              type="button"
              role="tab"
              aria-selected={page.path === path}
              className={page.path === path ? 'tab tab-active' : 'tab'}
              onClick={() => setPath(page.path)}
            >
              {page.path}
            </button>
          ))}
        </div>
        <div className="preview-actions">
          <button type="button" onClick={() => setNonce((value) => value + 1)}>
            重新加载
          </button>
          {current ? (
            <>
              <CopyButton value={current.preview_url} label="复制预览地址" />
              <CopyButton value={current.collect_url} label="复制采集地址" />
              <a href={current.preview_url} target="_blank" rel="noreferrer">
                新标签页打开
              </a>
            </>
          ) : null}
        </div>
      </div>

      <div className="preview-meta">
        <span className="badge">revision {revision}</span>
        {activeScenarioTitle ? (
          <span className="badge badge-scenario">{activeScenarioTitle}</span>
        ) : (
          <span className="badge badge-manual">手动编辑的状态</span>
        )}
        {current ? <span className="preview-purpose">{current.purpose}</span> : null}
      </div>

      {current ? (
        <div
          className="preview-shell"
          ref={shell}
          style={{ height: `${Math.round(height * scale)}px` }}
        >
          <iframe
            ref={frame}
            key={`${path}-${revision}-${nonce}`}
            className="preview-frame"
            title={`预览 ${path}`}
            src={src}
            style={{
              width: `${DESKTOP_WIDTH}px`,
              height: `${height}px`,
              transform: `scale(${scale})`,
            }}
            onLoad={() => {
              // Grow the frame to the rendered page so nothing is clipped;
              // a fixed height would hide the sections the user is checking.
              const doc = frame.current?.contentDocument
              const measured = doc?.documentElement?.scrollHeight ?? 0
              if (measured > 200) setHeight(Math.min(measured, 2600))
            }}
            // The preview is same-origin with the admin listener only by accident
            // of deployment; sandbox it so a target page can never script the
            // admin. Scripts must run: the CSR pages render in the browser.
            sandbox="allow-scripts allow-same-origin"
          />
        </div>
      ) : (
        <p className="hint">没有可预览的页面。</p>
      )}
    </div>
  )
}
