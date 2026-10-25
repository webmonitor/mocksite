/**
 * Paginated target page.
 *
 * First screen is page 1; each click appends exactly one page, the button is
 * disabled while loading, and it disappears after the last page. An empty list
 * still reaches `data-ready="true"` so "empty" never looks like "failed".
 */
(function (global) {
  'use strict'

  var shared = global.MocksiteList
  var state = { items: [], pageSize: 1, pageIndex: 0, loading: false }

  function hasMore() {
    return (state.pageIndex + 1) * state.pageSize < state.items.length
  }

  function syncButton() {
    var button = document.getElementById('load-more')
    if (!button) return
    button.disabled = state.loading
    button.hidden = !hasMore()
    button.textContent = state.loading ? 'Loading…' : 'Load more'
  }

  function loadNext(container) {
    if (state.loading || !hasMore()) return
    state.loading = true
    syncButton()
    // One macrotask so the disabled state is observable before rows appear.
    global.setTimeout(function () {
      shared.appendPage(container, state.items, state.pageSize, state.pageIndex + 1)
      state.pageIndex += 1
      state.loading = false
      syncButton()
    }, 0)
  }

  function start() {
    var container = document.getElementById('app')
    if (!container) return

    shared
      .fetchData()
      .then(function (data) {
        state.items = data.items
        state.pageSize = data.page_size
        container.innerHTML =
          '<div>' +
          '<h1>Deals</h1>' +
          '<table id="inventory">' +
          '<thead><tr><th>ID</th><th>Name</th><th>Price</th></tr></thead>' +
          '<tbody></tbody>' +
          '</table>' +
          '<button id="load-more" type="button">Load more</button>' +
          '<p id="status" data-state="pending">loading</p>' +
          '</div>'

        shared.appendPage(container, state.items, state.pageSize, 0)
        syncButton()
        shared.markReady(container, data.revision)

        var button = document.getElementById('load-more')
        if (button) {
          button.addEventListener('click', function () {
            loadNext(container)
          })
        }
      })
      .catch(function (error) {
        shared.showError(container, 'load failed: ' + error.message)
      })
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start)
  } else {
    start()
  }
})(window)
