/**
 * Product / list / review editor.
 *
 * Prices are edited and submitted as strings: parsing them into JS numbers
 * would silently round `128.50` and the server would reject the result anyway.
 * Drafts survive a failed submit; only a confirmed response clears them.
 *
 * The editor is tabbed because the product now has a lot of fields; showing
 * every field at once was a large part of why the old UI was hard to read.
 */

import { useEffect, useMemo, useState } from 'react'

import { Field, Notice } from '@/components/ui'
import { ApiError, type BusinessData, type Item, type Review } from '@/lib/api'

type Tab = 'product' | 'items' | 'reviews'

interface Draft {
  productId: string
  name: string
  brand: string
  sku: string
  currentPrice: string
  originalPrice: string
  currency: string
  rating: string
  stockStatus: string
  stockCount: string
  description: string
  pageSize: string
  items: Item[]
  reviews: Review[]
}

function toDraft(business: BusinessData): Draft {
  return {
    productId: business.product.id,
    name: business.product.name,
    brand: business.product.brand,
    sku: business.product.sku,
    currentPrice: business.product.current_price,
    originalPrice: business.product.original_price,
    currency: business.product.currency,
    rating: business.product.rating,
    stockStatus: business.product.stock_status,
    stockCount: String(business.product.stock_count),
    description: business.product.description,
    pageSize: String(business.page_size),
    items: business.items.map((item) => ({ ...item })),
    reviews: business.reviews.map((review) => ({ ...review })),
  }
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
  const [tab, setTab] = useState<Tab>('product')
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

  const updateItem = (index: number, field: keyof Item, value: string) => {
    setDraft((current) => ({
      ...current,
      items: current.items.map((item, at) => (at === index ? { ...item, [field]: value } : item)),
    }))
  }

  const updateReview = (index: number, field: keyof Review, value: string | number) => {
    setDraft((current) => ({
      ...current,
      reviews: current.reviews.map((review, at) =>
        at === index ? { ...review, [field]: value } : review,
      ),
    }))
  }

  const submit = async () => {
    setSaving(true)
    setErrors(new Map())
    setMessage(null)
    const pageSize = Number(draft.pageSize)
    const stockCount = Number(draft.stockCount)
    try {
      await onSave({
        business: {
          product: {
            id: draft.productId,
            name: draft.name,
            brand: draft.brand,
            sku: draft.sku,
            current_price: draft.currentPrice,
            original_price: draft.originalPrice,
            currency: draft.currency,
            rating: draft.rating,
            stock_status: draft.stockStatus,
            stock_count: Number.isFinite(stockCount) ? stockCount : draft.stockCount,
            description: draft.description,
          },
          items: draft.items,
          reviews: draft.reviews,
          page_size: Number.isFinite(pageSize) ? pageSize : draft.pageSize,
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
      <div className="editor-tabs" role="tablist" aria-label="编辑内容">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'product'}
          className={tab === 'product' ? 'tab tab-active' : 'tab'}
          onClick={() => setTab('product')}
        >
          商品字段
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'items'}
          className={tab === 'items' ? 'tab tab-active' : 'tab'}
          onClick={() => setTab('items')}
        >
          列表行 ({draft.items.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'reviews'}
          className={tab === 'reviews' ? 'tab tab-active' : 'tab'}
          onClick={() => setTab('reviews')}
        >
          评价 ({draft.reviews.length})
        </button>
      </div>

      {tab === 'product' ? (
        <>
          <div className="grid">
            <Field label="商品 ID" htmlFor="product-id" error={errors.get('business.product.id')}>
              <input
                id="product-id"
                value={draft.productId}
                onChange={(e) => set('productId', e.target.value)}
              />
            </Field>
            <Field
              label="商品名称"
              htmlFor="product-name"
              error={errors.get('business.product.name')}
            >
              <input
                id="product-name"
                value={draft.name}
                onChange={(e) => set('name', e.target.value)}
              />
            </Field>
            <Field label="品牌" htmlFor="product-brand" error={errors.get('business.product.brand')}>
              <input
                id="product-brand"
                value={draft.brand}
                onChange={(e) => set('brand', e.target.value)}
              />
            </Field>
            <Field label="SKU" htmlFor="product-sku" error={errors.get('business.product.sku')}>
              <input
                id="product-sku"
                value={draft.sku}
                onChange={(e) => set('sku', e.target.value)}
              />
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
                onChange={(e) => set('currentPrice', e.target.value)}
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
                onChange={(e) => set('originalPrice', e.target.value)}
              />
            </Field>
            <Field label="币种" htmlFor="product-currency" error={errors.get('business.product.currency')}>
              <input
                id="product-currency"
                value={draft.currency}
                maxLength={3}
                onChange={(e) => set('currency', e.target.value)}
              />
            </Field>
            <Field
              label="评分（0–5）"
              htmlFor="product-rating"
              error={errors.get('business.product.rating')}
              hint="十进制字符串，如 4.6"
            >
              <input
                id="product-rating"
                inputMode="decimal"
                value={draft.rating}
                onChange={(e) => set('rating', e.target.value)}
              />
            </Field>
            <Field label="库存状态" htmlFor="product-stock-status">
              <select
                id="product-stock-status"
                value={draft.stockStatus}
                onChange={(e) => set('stockStatus', e.target.value)}
              >
                <option value="in_stock">in_stock（有货）</option>
                <option value="low_stock">low_stock（库存紧张）</option>
                <option value="out_of_stock">out_of_stock（缺货）</option>
                <option value="preorder">preorder（预售）</option>
              </select>
            </Field>
            <Field
              label="库存数量"
              htmlFor="product-stock-count"
              error={errors.get('business.product.stock_count')}
            >
              <input
                id="product-stock-count"
                inputMode="numeric"
                value={draft.stockCount}
                onChange={(e) => set('stockCount', e.target.value)}
              />
            </Field>
            <Field label="页大小" htmlFor="page-size" error={errors.get('business.page_size')} hint="1–100">
              <input
                id="page-size"
                inputMode="numeric"
                value={draft.pageSize}
                onChange={(e) => set('pageSize', e.target.value)}
              />
            </Field>
          </div>

          <Field
            label="商品描述"
            htmlFor="product-description"
            error={errors.get('business.product.description')}
          >
            <textarea
              id="product-description"
              rows={4}
              value={draft.description}
              onChange={(e) => set('description', e.target.value)}
            />
          </Field>
        </>
      ) : null}

      {tab === 'items' ? (
        <>
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
                      <span className="error">{errors.get(`business.items.${index}.price}`)}</span>
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
          </div>
        </>
      ) : null}

      {tab === 'reviews' ? (
        <>
          <p className="hint">
            评价在页面上是浏览器端分页加载的：先渲染骨架屏，取到数据后才设置
            <code>#reviews[data-ready="true"]</code>。这里编辑的是数据源，不是 DOM。
          </p>
          <table className="rows">
            <thead>
              <tr>
                <th>作者</th>
                <th>评分</th>
                <th>日期</th>
                <th>标题</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {draft.reviews.map((review, index) => (
                <tr key={`${review.id}-${index}`}>
                  <td>
                    <input
                      aria-label={`第 ${index + 1} 条评价作者`}
                      value={review.author}
                      onChange={(e) => updateReview(index, 'author', e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      aria-label={`第 ${index + 1} 条评价评分`}
                      inputMode="numeric"
                      value={String(review.rating)}
                      onChange={(e) => updateReview(index, 'rating', Number(e.target.value))}
                    />
                  </td>
                  <td>
                    <input
                      aria-label={`第 ${index + 1} 条评价日期`}
                      value={review.date}
                      onChange={(e) => updateReview(index, 'date', e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      aria-label={`第 ${index + 1} 条评价标题`}
                      value={review.title}
                      onChange={(e) => updateReview(index, 'title', e.target.value)}
                    />
                  </td>
                  <td>
                    <button
                      type="button"
                      className="link"
                      onClick={() =>
                        setDraft((current) => ({
                          ...current,
                          reviews: current.reviews.filter((_, at) => at !== index),
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
        </>
      ) : null}

      <div className="actions sticky-actions">
        <button type="button" className="primary" onClick={() => void submit()} disabled={saving || !dirty}>
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
