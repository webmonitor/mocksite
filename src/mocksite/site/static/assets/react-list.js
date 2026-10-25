/**
 * React target page (vendored React 18 UMD, no build step).
 *
 * Renders into #app; readiness and revision are set on #app only after the
 * rows are actually in the DOM, which is what a browser collector waits for.
 */
(function (global) {
  'use strict'

  var shared = global.MocksiteList
  var e = global.React.createElement

  function List(props) {
    return e(
      'div',
      null,
      e('h1', null, 'Inventory'),
      e(
        'table',
        { id: 'inventory' },
        e(
          'thead',
          null,
          e('tr', null, e('th', null, 'ID'), e('th', null, 'Name'), e('th', null, 'Price')),
        ),
        e(
          'tbody',
          null,
          props.items.map(function (item) {
            return e(
              'tr',
              { key: item.id + '-' + item.name, className: 'item', 'data-id': item.id },
              e('td', { className: 'id' }, item.id),
              e('td', { className: 'name' }, item.name),
              e(
                'td',
                { className: props.itemPrice === 'renamed' ? 'cost' : 'price' },
                item.price,
              ),
            )
          }),
        ),
      ),
      e('p', { id: 'status', 'data-state': 'pending' }, 'loading'),
    )
  }

  function mount(container, data) {
    var root = global.ReactDOM.createRoot(container)
    root.render(e(List, { items: data.items, itemPrice: shared.page.itemPrice }))
    // Rendering is synchronous for this tree, so readiness can be set right
    // after render; if React ever batches, the collector would still wait for
    // data-ready rather than a fixed timeout.
    shared.markReady(container, data.revision)
  }

  function start() {
    var container = document.getElementById('app')
    if (!container) return
    shared
      .fetchData()
      .then(function (data) {
        mount(container, data)
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
