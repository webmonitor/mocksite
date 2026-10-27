/**
 * Notice-detail page behaviour.
 *
 * This is the page that makes a collector do real work:
 *
 *   #view-count[data-loaded="true"]  the portal's `_showDynClicks`: the count is
 *                                    empty in the static HTML and filled by
 *                                    this script after a fetch
 *   #notice-body                     real paragraphs, one per entry
 *
 * Also implemented because real portals have them and collectors trip over
 * them: the withdrawn banner toggle, and a "打印" action that reports state in
 * the DOM instead of navigating.
 */
(function (global) {
  'use strict'

  var CONFIG = {}
  try {
    CONFIG = JSON.parse(document.getElementById('mocksite-notice').textContent)
  } catch (error) {
    CONFIG = {}
  }

  function status(text, state) {
    var node = document.getElementById('view-status')
    if (!node) return
    node.textContent = text
    node.setAttribute('data-state', state)
  }

  /**
   * The click counter is deliberately asynchronous: a collector that reads
   * `#view-count` right after `domcontentloaded` gets an empty string, exactly
   * like the portal this page imitates.
   */
  function loadViewCount() {
    var node = document.getElementById('view-count')
    if (!node) return
    fetch('/api/views', { headers: { Accept: 'application/json' }, cache: 'no-store' })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status)
        return response.json()
      })
      .then(function (data) {
        var count = Number(data && data.views)
        node.textContent = Number.isFinite(count) ? String(count) : ''
        node.setAttribute('data-loaded', 'true')
        node.setAttribute('data-revision', String(data && data.revision))
        status('点击次数已加载', 'ready')
      })
      .catch(function () {
        // Leaves data-loaded="false": "not loaded" must stay distinguishable
        // from "zero views".
        node.textContent = ''
        node.setAttribute('data-loaded', 'false')
        status('点击次数加载失败', 'error')
      })
  }

  function startPrint() {
    var button = document.getElementById('print-notice')
    if (!button) return
    button.addEventListener('click', function () {
      var printed = button.getAttribute('data-printed') === 'true'
      button.setAttribute('data-printed', String(!printed))
      button.textContent = printed ? '打印本页' : '已发送打印'
    })
  }

  function startAttachments() {
    var links = document.querySelectorAll('.attachment-name')
    Array.prototype.forEach.call(links, function (link) {
      link.addEventListener('click', function (event) {
        // A demo portal has no real files behind the links; report the click
        // in the DOM rather than navigating away from the notice.
        event.preventDefault()
        link.setAttribute('data-clicked', 'true')
      })
    })
  }

  function start() {
    loadViewCount()
    startPrint()
    startAttachments()
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start)
  } else {
    start()
  }
})(window)
