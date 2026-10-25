/**
 * Product / list editor.
 *
 * Prices are edited and submitted as strings: parsing them into JS numbers
 * would silently round `128.50` and the server would reject the result anyway.
 * Drafts survive a failed submit; only a confirmed response clears them.
 */

import { useEffect, useMemo, useState } from 'react'

import { Field, Notice } from '@/components/ui'
import { ApiError, type BusinessData, type Item } from '@/lib/api'

interface Draft {
  productId: string
  name: string
  currentPrice: string
  originalPrice: string
  currency: string
  pageSize: string
  items: Item[]
}

function toDraft(business: BusinessData): Draft {
  return {
    productId: business.product.id,
    name: business.product.name,
    currentPrice: business.product.current_price,
    originalPrice: business.product.original_price,
    currency: business.product.currency,
    pageSize: String(business.page_size),
    items: business.items.map((item) => ({ ...item })),
  }
}

export function BusinessEditor({
  business,
  onSave,
}: {
  business: BusinessData
  onSave: (patch: unknown) => Promise<void>
}) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(business))
  const [errors, setErrors] = useState<Map<string, string>>(new Map())
  const [message, setMessage] = useState<{ kind: 'ok' | 'error' | 'info'; text: string } | null>(null)
  const [saving, setSaving] = useState(false)

  const saved = useMemo(() => toDraft(business), [business])
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved)

  // A server-side change (scenario/reset) replaces the draft, because the UI
  // must not keep showing edits that the server no longer has.
  useEffect(() => {
    setDraft(toDraft(business))
    setErrors(new Map())
  }, [business])

  const updateItem = (index: number, field: keyof Item, value: string) => {
    setDraft((current) => ({
      ...current,
      items: current.items.map((item, at) => (at === index ? { ...item, [field]: value } : item)),
    }))
  }

  const submit = async () => {
    setSaving(true)
    setErrors(new Map())
    setMessage(null)
    const pageSize = Number(draft.pageSize)
    try {
      await onSave({
        business: {
          product: {
            id: draft.productId,
            name: draft.name,
            current_price: draft.currentPrice,
            original_price: draft.originalPrice,
            currency: draft.currency,
          },
          items: draft.items,
          page_size: Number.isFinite(pageSize) ? pageSize : draft.pageSize,
        },
      })
      setMessage({ kind: 'ok', text: '已保存' })
    } catch (cause) {
      if (cause instanceof ApiError) {
        setErrors(cause.fieldErrors())
        setMessage({ kind: 'error', text: `保存失败（${cause.code}），修改内容已保留` })
      } else {
        setMessage({ kind: 'error', text: '保存失败，修改内容已保留' })
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="editor">
      <div className="grid">
        <Field label="商品 ID" htmlFor="product-id" error={errors.get('business.product.id')}>
          <input id="product-id" value={draft.productId} onChange={(e) => setDraft((c) => ({ ...c, productId: e.target.value }))} />
        </Field>
        <Field label="商品名称" htmlFor="product-name" error={errors.get('business.product.name')}>
          <input id="product-name" value={draft.name} onChange={(e) => setDraft((c) => ({ ...c, name: e.target.value }))} />
        </Field>
        <Field
          label="现价（十进制字符串）"
          htmlFor="product-current-price"
          error={errors.get('business.product.current_price')}
          hint="例如 128.50；不接受浮点、指数或负数"
        >
          <input
            id="product-current-price"
            inputMode="decimal"
            value={draft.currentPrice}
            onChange={(e) => setDraft((c) => ({ ...c, currentPrice: e.target.value }))}
          />
        </Field>
        <Field
          label="原价"
          htmlFor="product-original-price"
          error={errors.get('business.product.original_price')}
        >
          <input
            id="product-original-price"
            inputMode="decimal"
            value={draft.originalPrice}
            onChange={(e) => setDraft((c) => ({ ...c, originalPrice: e.target.value }))}
          />
        </Field>
        <Field label="币种" htmlFor="product-currency" error={errors.get('business.product.currency')}>
          <input
            id="product-currency"
            value={draft.currency}
            maxLength={3}
            onChange={(e) => setDraft((c) => ({ ...c, currency: e.target.value }))}
          />
        </Field>
        <Field label="页大小" htmlFor="page-size" error={errors.get('business.page_size')} hint="1–100">
          <input
            id="page-size"
            inputMode="numeric"
            value={draft.pageSize}
            onChange={(e) => setDraft((c) => ({ ...c, pageSize: e.target.value }))}
          />
        </Field>
      </div>

      <h3>列表行</h3>
      <table className="rows">
        <thead>
          <tr>
            <th>ID</th>
            <th>名称</th>
            <th>价格</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {draft.items.map((item, index) => (
            <tr key={`${item.id}-${index}`}>
              <td>
                <input
                  aria-label={`第 ${index + 1} 行 ID`}
                  value={item.id}
                  onChange={(e) => updateItem(index, 'id', e.target.value)}
                />
                {errors.get(`business.items.${index}.id`) ? (
                  <span className="error">{errors.get(`business.items.${index}.id`)}</span>
                ) : null}
              </td>
              <td>
                <input
                  aria-label={`第 ${index + 1} 行名称`}
                  value={item.name}
                  onChange={(e) => updateItem(index, 'name', e.target.value)}
                />
              </td>
              <td>
                <input
                  aria-label={`第 ${index + 1} 行价格`}
                  inputMode="decimal"
                  value={item.price}
                  onChange={(e) => updateItem(index, 'price', e.target.value)}
                />
                {errors.get(`business.items.${index}.price`) ? (
                  <span className="error">{errors.get(`business.items.${index}.price`)}</span>
                ) : null}
              </td>
              <td>
                <button
                  type="button"
                  className="link"
                  onClick={() =>
                    setDraft((current) => ({
                      ...current,
                      items: current.items.filter((_, at) => at !== index),
                    }))
                  }
                >
                  删除
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="actions">
        <button
          type="button"
          onClick={() =>
            setDraft((current) => ({
              ...current,
              items: [...current.items, { id: '', name: '', price: '0.00' }],
            }))
          }
        >
          添加行
        </button>
        <button type="button" className="primary" onClick={() => void submit()} disabled={saving || !dirty}>
          {saving ? '保存中…' : '保存商品与列表'}
        </button>
        <button type="button" onClick={() => setDraft(toDraft(business))} disabled={saving || !dirty}>
          放弃修改
        </button>
      </div>

      {dirty ? <Notice kind="info">有未保存的修改；当前页面仍显示已生效的状态。</Notice> : null}
      {message ? <Notice kind={message.kind}>{message.text}</Notice> : null}
    </div>
  )
}
