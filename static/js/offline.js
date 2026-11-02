/* Strona /offline: lista przepisów i wpisów zapisanych przez service worker w pamięci urządzenia. */
(function () {
  "use strict";
  if (!("caches" in window)) return;

  function titleFrom(html) {
    var doc = new DOMParser().parseFromString(html, "text/html");
    var h1 = doc.querySelector("h1");
    return (h1 ? h1.textContent : doc.title || "").trim();
  }

  function fill(listEl, entries) {
    if (!listEl || !entries.length) return;
    listEl.textContent = "";
    entries.sort(function (a, b) { return a.title.localeCompare(b.title, "pl"); });
    entries.forEach(function (e) {
      var li = document.createElement("li");
      var a = document.createElement("a");
      a.href = e.path;
      a.textContent = e.title || e.path;
      li.appendChild(a);
      listEl.appendChild(li);
    });
  }

  caches.keys().then(function (names) {
    var pageCaches = names.filter(function (n) { return n.indexOf("pages-") === 0; });
    return Promise.all(pageCaches.map(function (name) {
      return caches.open(name).then(function (cache) {
        return cache.keys().then(function (requests) {
          return Promise.all(requests.map(function (req) {
            var path = new URL(req.url).pathname;
            if (!/^\/(przepis|blog)\/[^/]+$/.test(path)) return null;
            return cache.match(req).then(function (res) {
              return res.text().then(function (html) { return { path: path, title: titleFrom(html) }; });
            });
          }));
        });
      });
    }));
  }).then(function (groups) {
    var all = [].concat.apply([], groups).filter(Boolean);
    fill(document.querySelector("[data-offline-recipes]"), all.filter(function (e) { return e.path.indexOf("/przepis/") === 0; }));
    fill(document.querySelector("[data-offline-posts]"), all.filter(function (e) { return e.path.indexOf("/blog/") === 0; }));
  });
})();
