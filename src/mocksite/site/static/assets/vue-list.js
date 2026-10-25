/**
 * Vue target page (vendored Vue 3 global build, no build step).
 *
 * Same DOM contract as the React page: #app[data-ready="true"] and
 * #app[data-revision] are set after the rows exist.
 */
(function (global) {
  'use strict'

  var shared = global.MocksiteList

  function start() {
    var container = document.getElementById('app')
    if (!container) return

    shared
      .fetchData()
      .then(function (data) {
        var app = global.Vue.createApp({
          data: function () {
            return {
              items: data.items,
              itemPrice: shared.page.itemPrice,
            }
          },
          template:
            '<div>' +
            '<h1>Inventory</h1>' +
            '<table id="inventory">' +
            '<thead><tr><th>ID</th><th>Name</th><th>Price</th></tr></thead>' +
            '<tbody>' +
            '<tr v-for="item in items" :key="item.id + \'-\' + item.name" class="item" :data-id="item.id">' +
            '<td class="id">{{ item.id }}</td>' +
            '<td class="name">{{ item.name }}</td>' +
            '<td :class="itemPrice === \'renamed\' ? \'cost\' : \'price\'">{{ item.price }}</td>' +
            '</tr>' +
            '</tbody>' +
            '</table>' +
            '<p id="status" data-state="pending">loading</p>' +
            '</div>',
          mounted: function () {
            // `nextTick` guarantees the rows are in the DOM before readiness is
            // advertised.
            var vm = this
            global.Vue.nextTick(function () {
              shared.markReady(container, data.revision)
              vm.$el.setAttribute('data-mounted', 'true')
            })
          },
        })
        app.mount(container)
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
