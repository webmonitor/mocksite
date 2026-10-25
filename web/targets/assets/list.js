/**
 * Shared list bootstrap for the React and Vue target pages.
 *
 * Vendored UMD build (no bundler, no CDN): this file is served as-is and talks
 * to the DOM directly. It owns the two contracts a collector depends on:
 *
 *   #app[data-ready="true"]  set only after data loaded and rows rendered
 *   #app[data-revision]      the revision the rendered rows came from
 *
 * On failure the error state is shown and `data-ready` is left unset, so
 * "empty list" and "load failed" are distinguishable.
 */
(function (global) {
  'use strict'

  var PAGE = global.MOCKSITE_LIST || {}

  function renderRows(container, items, options) {
    var tbody = container.querySelector('#inventory tbody')
    if (!tbody) throw new Error('missing #inventory tbody')
    tbody.textContent = ''

    for (var index = 0; index < items.length; index += 1) {
      var item = items[index]
      var row = document.createElement('tr')
      row.className = 'item'
      row.setAttribute('data-id', item.id)

      var idCell = document.createElement('td')
      idCell.className = 'id'
      idCell.textContent = item.id

      var nameCell = document.createElement('td')
      nameCell.className = 'name'
      nameCell.textContent = item.name

      var priceCell = document.createElement('td')
      priceCell.className = 'price'
      priceCell.textContent = item.price

      row.appendChild(idCell)
      row.appendChild(nameCell)
      row.appendChild(priceCell)
      tbody.appendChild(row)
    }
  }

  function appendPage(container, items, pageSize, pageIndex) {
    var slice = items.slice(pageIndex * pageSize, (pageIndex + 1) * pageSize)
    var tbody = container.querySelector('#inventory tbody')
    for (var index = 0; index < slice.length; index += 1) {
      var item = slice[index]
      var row = document.createElement('tr')
      row.className = 'item'
      row.setAttribute('data-id', item.id)

      var idCell = document.createElement('td')
      idCell.className = 'id'
      idCell.textContent = item.id
      var nameCell = document.createElement('td')
      nameCell.className = 'name'
      nameCell.textContent = item.name
      var priceCell = document.createElement('td')
      priceCell.className = 'price'
      priceCell.textContent = item.price

      row.appendChild(idCell)
      row.appendChild(nameCell)
      row.appendChild(priceCell)
      tbody.appendChild(row)
    }
    return slice.length
  }

  function showError(container, message) {
    var status = container.querySelector('#status')
    if (status) {
      status.textContent = message
      status.setAttribute('data-state', 'error')
    }
    container.removeAttribute('data-ready')
  }

  function fetchData() {
    return fetch('/api/data', { headers: { Accept: 'application/json' }, cache: 'no-store' }).then(
      function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status)
        return response.json()
      },
    )
  }

  function markReady(container, revision) {
    container.setAttribute('data-revision', String(revision))
    container.setAttribute('data-ready', 'true')
    var status = container.querySelector('#status')
    if (status) {
      status.textContent = 'ready'
      status.setAttribute('data-state', 'ready')
    }
  }

  global.MocksiteList = {
    page: PAGE,
    renderRows: renderRows,
    appendPage: appendPage,
    showError: showError,
    fetchData: fetchData,
    markReady: markReady,
  }
})(window)
