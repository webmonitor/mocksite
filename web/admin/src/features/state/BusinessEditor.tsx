/**
 * Notice editor.
 *
 * Amounts are edited and submitted as strings: parsing them into JS numbers
 * would silently round `128.50` and the server would reject the result anyway.
 * Drafts survive a failed submit; only a confirmed response clears them.
 */

import { useEffect, useMemo, useState } from 'react'

import { Field, Notice } from '@/components/ui'
import { ApiError, type BusinessData } from '@/lib/api'

interface Draft {
  noticeId: string
  title: string
  department: string
  docNo: string
  category: string
  currentFee: string
  previousFee: string
  currency: string
  publishedAt: string
  effectiveDate: string
  viewCount: string
  status: string
  bodyText: string
  prevTitle: string
  nextTitle: string
}

function toDraft(business: BusinessData): Draft {
  return {
    noticeId: business.notice.id,
    title: business.notice.title,
    department: business.notice.department,
    docNo: business.notice.doc_no,
    category: business.notice.category,
    currentFee: business.notice.current_fee,
    previousFee: business.notice.previous_fee,
    currency: business.notice.currency,
    publishedAt: business.notice.published_at,
    effectiveDate: business.notice.effective_date,
    viewCount: String(business.notice.view_count),
    status: business.notice.status,
    bodyText: business.notice.body.join('\n'),
    prevTitle: business.notice.prev_title,
    nextTitle: business.notice.next_title,
  }
}

/** One paragraph per line: an empty line would violate the min-length rule. */
function toBody(text: string): string[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
}

export function BusinessEditor({
  business,
  onSave,
  onDirtyChange,
}: {
  business: BusinessData
  onSave: (patch: unknown) => Promise<void>
  onDirtyChange?: (dirty: boolean) => void
}) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(business))
  const [errors, setErrors] = useState<Map<string, string>>(new Map())
  const [message, setMessage] = useState<{ kind: 'ok' | 'error' | 'info'; text: string } | null>(
    null,
  )
  const [saving, setSaving] = useState(false)

  const saved = useMemo(() => toDraft(business), [business])
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved)

  useEffect(() => {
    onDirtyChange?.(dirty)
  }, [dirty, onDirtyChange])

  // A server-side change (scenario/reset) replaces the draft, because the UI
  // must not keep showing edits that the server no longer has.
  useEffect(() => {
    setDraft(toDraft(business))
    setErrors(new Map())
  }, [business])

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((current) => ({ ...current, [key]: value }))

  const submit = async () => {
    setSaving(true)
    setErrors(new Map())
    setMessage(null)
    const viewCount = Number(draft.viewCount)
    try {
      await onSave({
        business: {
          notice: {
            id: draft.noticeId,
            title: draft.title,
            department: draft.department,
            doc_no: draft.docNo,
            category: draft.category,
            current_fee: draft.currentFee,
            previous_fee: draft.previousFee,
            currency: draft.currency,
            published_at: draft.publishedAt,
            effective_date: draft.effectiveDate,
            view_count: Number.isFinite(viewCount) ? viewCount : draft.viewCount,
            status: draft.status,
            body: toBody(draft.bodyText),
            prev_title: draft.prevTitle,
            next_title: draft.nextTitle,
          },
        },
      })
      setMessage({ kind: 'ok', text: '已保存，右侧预览已更新。' })
    } catch (cause) {
      if (cause instanceof ApiError) {
        setErrors(cause.fieldErrors())
        setMessage({ kind: 'error', text: `${cause.humanMessage} 修改内容已保留。` })
      } else {
        setMessage({ kind: 'error', text: '保存失败，修改内容已保留。' })
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="editor">
      <div className="grid">
        <Field label="通知 ID" htmlFor="notice-id" error={errors.get('business.notice.id')}>
          <input
            id="notice-id"
            value={draft.noticeId}
            onChange={(e) => set('noticeId', e.target.value)}
          />
        </Field>
        <Field label="标题" htmlFor="notice-title" error={errors.get('business.notice.title')}>
          <input
            id="notice-title"
            value={draft.title}
            onChange={(e) => set('title', e.target.value)}
          />
        </Field>
        <Field
          label="发布单位"
          htmlFor="notice-department"
          error={errors.get('business.notice.department')}
        >
          <input
            id="notice-department"
            value={draft.department}
            onChange={(e) => set('department', e.target.value)}
          />
        </Field>
        <Field label="文号" htmlFor="notice-doc-no" error={errors.get('business.notice.doc_no')}>
          <input
            id="notice-doc-no"
            value={draft.docNo}
            onChange={(e) => set('docNo', e.target.value)}
          />
        </Field>
        <Field label="分类" htmlFor="notice-category" error={errors.get('business.notice.category')}>
          <input
            id="notice-category"
            value={draft.category}
            onChange={(e) => set('category', e.target.value)}
          />
        </Field>
        <Field
          label="现行标准（十进制字符串）"
          htmlFor="notice-current-fee"
          error={errors.get('business.notice.current_fee')}
          hint="例如 128.50；不接受浮点、指数或负数"
        >
          <input
            id="notice-current-fee"
            inputMode="decimal"
            value={draft.currentFee}
            onChange={(e) => set('currentFee', e.target.value)}
          />
        </Field>
        <Field
          label="原标准"
          htmlFor="notice-previous-fee"
          error={errors.get('business.notice.previous_fee')}
        >
          <input
            id="notice-previous-fee"
            inputMode="decimal"
            value={draft.previousFee}
            onChange={(e) => set('previousFee', e.target.value)}
          />
        </Field>
        <Field label="币种" htmlFor="notice-currency" error={errors.get('business.notice.currency')}>
          <input
            id="notice-currency"
            value={draft.currency}
            maxLength={3}
            onChange={(e) => set('currency', e.target.value)}
          />
        </Field>
        <Field
          label="发布时间"
          htmlFor="notice-published-at"
          error={errors.get('business.notice.published_at')}
          hint="YYYY-MM-DD HH:MM；页面上的三种日期都由它派生"
        >
          <input
            id="notice-published-at"
            value={draft.publishedAt}
            onChange={(e) => set('publishedAt', e.target.value)}
          />
        </Field>
        <Field
          label="执行日期"
          htmlFor="notice-effective-date"
          error={errors.get('business.notice.effective_date')}
          hint="YYYY-MM-DD"
        >
          <input
            id="notice-effective-date"
            value={draft.effectiveDate}
            onChange={(e) => set('effectiveDate', e.target.value)}
          />
        </Field>
        <Field label="状态" htmlFor="notice-status" error={errors.get('business.notice.status')}>
          <select
            id="notice-status"
            value={draft.status}
            onChange={(e) => set('status', e.target.value)}
          >
            <option value="published">published（已发布）</option>
            <option value="withdrawn">withdrawn（已撤回）</option>
          </select>
        </Field>
        <Field
          label="点击次数"
          htmlFor="notice-view-count"
          error={errors.get('business.notice.view_count')}
          hint="页面由脚本异步填充，静态 HTML 里为空"
        >
          <input
            id="notice-view-count"
            inputMode="numeric"
            value={draft.viewCount}
            onChange={(e) => set('viewCount', e.target.value)}
          />
        </Field>
        <Field
          label="上一篇标题"
          htmlFor="notice-prev-title"
          error={errors.get('business.notice.prev_title')}
          hint="页面导航，不是本页内容；整页文本比对会误判"
        >
          <input
            id="notice-prev-title"
            value={draft.prevTitle}
            onChange={(e) => set('prevTitle', e.target.value)}
          />
        </Field>
        <Field
          label="下一篇标题"
          htmlFor="notice-next-title"
          error={errors.get('business.notice.next_title')}
        >
          <input
            id="notice-next-title"
            value={draft.nextTitle}
            onChange={(e) => set('nextTitle', e.target.value)}
          />
        </Field>
      </div>

      <Field
        label="正文（每行一段）"
        htmlFor="notice-body"
        error={errors.get('business.notice.body')}
      >
        <textarea
          id="notice-body"
          rows={8}
          value={draft.bodyText}
          onChange={(e) => set('bodyText', e.target.value)}
        />
      </Field>

      <div className="actions sticky-actions">
        <button
          type="button"
          className="primary"
          onClick={() => void submit()}
          disabled={saving || !dirty}
        >
          {saving ? '保存中…' : '保存修改'}
        </button>
        <button type="button" onClick={() => setDraft(toDraft(business))} disabled={saving || !dirty}>
          放弃修改
        </button>
        {dirty ? <span className="hint">有未保存的修改；页面仍显示已生效的状态。</span> : null}
      </div>

      {message ? <Notice kind={message.kind}>{message.text}</Notice> : null}
    </div>
  )
}
