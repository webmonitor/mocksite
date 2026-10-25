/**
 * Product-detail page behaviour.
 *
 * This is the page that makes a collector do real work:
 *
 *   #reviews[data-ready="true"]  set only after the first page of reviews has
 *                                actually been rendered (the skeletons in the
 *                                static HTML must never look ready)
 *   #reviews[data-revision]      the revision the rendered reviews came from
 *
 * Also implemented, because real shops have them and collectors trip over
 * them: gallery switching, variant selection, quantity stepper and a
 * wishlist button that reports state in the DOM.
 */
(function (global) {
  'use strict'

  var CONFIG = {}
  try {
    CONFIG = JSON.parse(document.getElementById('mocksite-product').textContent)
  } catch (error) {
    CONFIG = {}
  }

  var pageSize = Number(CONFIG.reviewPageSize) || 2
  var reviews = { items: [], pageIndex: 0, loading: false }

  function status(text, state) {
    var node = document.getElementById('reviews-status')
    if (!node) return
    node.textContent = text
    node.setAttribute('data-state', state)
  }

  function starString(rating) {
    var full = Math.round(rating)
    var out = ''
    for (var i = 0; i < 5; i += 1) out += i < full ? '★' : '☆'
    return out
  }

  function renderReview(review) {
    var li = document.createElement('li')
    li.className = 'review-item'
    li.setAttribute('data-review-id', review.id)

    var head = document.createElement('div')
    head.className = 'review-head'

    var stars = document.createElement('span')
    stars.className = 'stars'
    stars.setAttribute('aria-label', review.rating + ' out of 5')
    stars.textContent = starString(review.rating)

    var author = document.createElement('span')
    author.className = 'review-author'
    author.textContent = review.author

    var date = document.createElement('time')
    date.className = 'review-date'
    date.setAttribute('datetime', review.date)
    date.textContent = review.date

    head.appendChild(stars)
    head.appendChild(author)
    head.appendChild(date)

    if (review.verified) {
      var badge = document.createElement('span')
      badge.className = 'verified-badge'
      badge.textContent = 'Verified purchase'
      head.appendChild(badge)
    }

    var title = document.createElement('h3')
    title.className = 'review-title'
    title.textContent = review.title

    var body = document.createElement('p')
    body.className = 'review-body'
    body.textContent = review.body

    li.appendChild(head)
    li.appendChild(title)
    li.appendChild(body)
    return li
  }

  function hasMore() {
    return (reviews.pageIndex + 1) * pageSize < reviews.items.length
  }

  function syncButton() {
    var button = document.getElementById('load-more-reviews')
    if (!button) return
    button.disabled = reviews.loading
    button.hidden = !hasMore()
    button.textContent = reviews.loading ? 'Loading…' : 'Load more reviews'
  }

  function appendPage() {
    var list = document.getElementById('reviews-list')
    if (!list) return 0
    var start = reviews.pageIndex * pageSize
    var slice = reviews.items.slice(start, start + pageSize)
    for (var i = 0; i < slice.length; i += 1) list.appendChild(renderReview(slice[i]))
    return slice.length
  }

  function markReady(revision) {
    var container = document.getElementById('reviews')
    if (!container) return
    container.setAttribute('data-revision', String(revision))
    container.setAttribute('data-ready', 'true')
  }

  function showError(message) {
    var container = document.getElementById('reviews')
    if (container) container.removeAttribute('data-ready')
    var list = document.getElementById('reviews-list')
    if (list) list.textContent = ''
    status(message, 'error')
  }

  function loadMore() {
    if (reviews.loading || !hasMore()) return
    reviews.loading = true
    syncButton()
    global.setTimeout(function () {
      appendPage()
      reviews.pageIndex += 1
      reviews.loading = false
      syncButton()
      status(
        reviews.pageIndex + ' of ' + Math.ceil(reviews.items.length / pageSize) + ' pages',
        'ready',
      )
    }, 0)
  }

  function startReviews() {
    var container = document.getElementById('reviews')
    if (!container) return

    fetch('/api/data', { headers: { Accept: 'application/json' }, cache: 'no-store' })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status)
        return response.json()
      })
      .then(function (data) {
        reviews.items = data.reviews || []
        reviews.pageIndex = 0
        var list = document.getElementById('reviews-list')
        if (list) list.textContent = ''
        appendPage()
        reviews.pageIndex = 1
        syncButton()
        markReady(data.revision)

        var total = document.getElementById('reviews-total')
        if (total && data.product) total.textContent = data.product.review_count

        status(
          reviews.items.length === 0
            ? 'No reviews yet'
            : reviews.pageIndex + ' of ' + Math.ceil(reviews.items.length / pageSize) + ' pages',
          'ready',
        )

        var button = document.getElementById('load-more-reviews')
        if (button) button.addEventListener('click', loadMore)
      })
      .catch(function (error) {
        showError('Could not load reviews: ' + error.message)
      })
  }

  function startGallery() {
    var main = document.getElementById('gallery-image')
    if (!main) return
    var buttons = document.querySelectorAll('[data-gallery-index]')
    Array.prototype.forEach.call(buttons, function (button) {
      button.addEventListener('click', function () {
        var index = Number(button.getAttribute('data-gallery-index'))
        var thumb = button.querySelector('img')
        if (!thumb) return
        main.src = thumb.src
        main.alt = button.getAttribute('aria-label') || main.alt
        Array.prototype.forEach.call(buttons, function (other) {
          other.setAttribute('aria-selected', String(other === button))
        })
      })
    })
  }

  function startVariants() {
    var groups = document.querySelectorAll('.variant-options')
    Array.prototype.forEach.call(groups, function (group) {
      var buttons = group.querySelectorAll('.variant-option')
      Array.prototype.forEach.call(buttons, function (button) {
        button.addEventListener('click', function () {
          if (button.disabled) return
          Array.prototype.forEach.call(buttons, function (other) {
            other.setAttribute('aria-pressed', String(other === button))
          })
          updateSelected()
        })
      })
    })
  }

  function updateSelected() {
    var target = document.getElementById('selected-variant')
    if (!target) return
    var pressed = document.querySelectorAll('.variant-option[aria-pressed="true"]')
    var labels = []
    Array.prototype.forEach.call(pressed, function (node) {
      labels.push(node.textContent.trim())
    })
    target.textContent = 'Selected: ' + labels.join(' / ')
  }

  function startQuantity() {
    var input = document.getElementById('qty')
    if (!input) return
    var decrease = document.getElementById('qty-decrease')
    var increase = document.getElementById('qty-increase')
    if (decrease) {
      decrease.addEventListener('click', function () {
        var value = Math.max(1, (parseInt(input.value, 10) || 1) - 1)
        input.value = String(value)
      })
    }
    if (increase) {
      increase.addEventListener('click', function () {
        var value = Math.min(99, (parseInt(input.value, 10) || 1) + 1)
        input.value = String(value)
      })
    }
  }

  function startWishlist() {
    var button = document.getElementById('add-to-wishlist')
    if (!button) return
    button.addEventListener('click', function () {
      var saved = button.getAttribute('data-saved') === 'true'
      button.setAttribute('data-saved', String(!saved))
      button.textContent = saved ? 'Save' : 'Saved'
    })
  }

  function start() {
    startGallery()
    startVariants()
    startQuantity()
    startWishlist()
    startReviews()
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start)
  } else {
    start()
  }
})(window)
